// The production Compose file historically invokes `curl -f` for MinIO's
// readiness check. This purpose-built static binary preserves that interface
// without adding a shell or a general-purpose HTTP client to the runtime image.
package main

import (
	"context"
	"fmt"
	"io"
	"net"
	"net/http"
	"net/url"
	"os"
	"time"
)

const readyURL = "http://localhost:9000/minio/health/ready"

func main() {
	if len(os.Args) != 3 || os.Args[1] != "-f" || os.Args[2] != readyURL {
		fmt.Fprintln(os.Stderr, "storage healthcheck accepts only the configured readiness endpoint")
		os.Exit(2)
	}

	target, err := url.Parse(readyURL)
	if err != nil || target.Scheme != "http" || target.Hostname() != "localhost" || target.Port() != "9000" {
		fmt.Fprintln(os.Stderr, "storage healthcheck configuration is invalid")
		os.Exit(2)
	}

	dialer := &net.Dialer{Timeout: 2 * time.Second}
	transport := &http.Transport{
		Proxy:               nil,
		DialContext:         dialer.DialContext,
		DisableKeepAlives:   true,
		MaxIdleConns:        0,
		IdleConnTimeout:     time.Second,
		TLSHandshakeTimeout: 2 * time.Second,
	}
	client := &http.Client{
		Transport: transport,
		Timeout:   4 * time.Second,
		CheckRedirect: func(_ *http.Request, _ []*http.Request) error {
			return http.ErrUseLastResponse
		},
	}

	request, err := http.NewRequestWithContext(context.Background(), http.MethodGet, target.String(), nil)
	if err != nil {
		fmt.Fprintln(os.Stderr, "storage healthcheck request could not be created")
		os.Exit(2)
	}
	response, err := client.Do(request)
	if err != nil {
		fmt.Fprintln(os.Stderr, "storage readiness check failed")
		os.Exit(1)
	}
	defer response.Body.Close()
	_, _ = io.Copy(io.Discard, io.LimitReader(response.Body, 4096))
	if response.StatusCode != http.StatusOK {
		fmt.Fprintln(os.Stderr, "storage is not ready")
		os.Exit(1)
	}
}
