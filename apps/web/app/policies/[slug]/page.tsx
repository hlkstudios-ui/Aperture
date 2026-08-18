import type { Metadata } from "next";
import { notFound } from "next/navigation";
import { SiteHeader } from "@/app/components/site-header";
import { approvedPolicy } from "@/app/lib/policies";

type Props = { params: Promise<{ slug: string }> };

export async function generateMetadata({ params }: Props): Promise<Metadata> {
  const policy = approvedPolicy((await params).slug);
  return policy ? { title: policy.title } : {};
}

export default async function PolicyPage({ params }: Props) {
  const policy = approvedPolicy((await params).slug);
  if (!policy) notFound();
  return <main className="catalog-page policy-page"><SiteHeader />
    <article>
      <p className="eyebrow">Approved policy · version {policy.version}</p>
      <h1>{policy.title}</h1>
      <p>Effective {new Date(policy.effective_at as string).toLocaleDateString("en-CA", { timeZone: "UTC" })}</p>
      {policy.sections.map((section) => <section key={section.heading}>
        <h2>{section.heading}</h2>
        {section.paragraphs.map((paragraph, index) => <p key={index}>{paragraph}</p>)}
      </section>)}
    </article>
  </main>;
}
