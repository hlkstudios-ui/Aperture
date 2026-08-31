import { describe, expect, it } from "vitest";
import {
  safeStudioDestination,
  studioDevelopmentAccessEnabled,
  studioDevelopmentAccessPath,
} from "./studio-development-access";

describe("Studio development access", () => {
  it("only enables automatic access in an explicitly enabled development runtime", () => {
    expect(studioDevelopmentAccessEnabled({
      NODE_ENV: "development",
      APP_ENV: "development",
      STUDIO_DEV_AUTO_LOGIN: "true",
    })).toBe(true);
    expect(studioDevelopmentAccessEnabled({
      NODE_ENV: "production",
      APP_ENV: "development",
      STUDIO_DEV_AUTO_LOGIN: "true",
    })).toBe(false);
    expect(studioDevelopmentAccessEnabled({
      NODE_ENV: "development",
      APP_ENV: "staging",
      STUDIO_DEV_AUTO_LOGIN: "true",
    })).toBe(false);
    expect(studioDevelopmentAccessEnabled({
      NODE_ENV: "development",
      APP_ENV: "development",
      STUDIO_DEV_AUTO_LOGIN: "false",
    })).toBe(false);
  });

  it("keeps only internal Studio destinations and their query strings", () => {
    expect(safeStudioDestination("/studio/uploads?status=ready")).toBe(
      "/studio/uploads?status=ready",
    );
    expect(safeStudioDestination("https://attacker.test/studio")).toBe("/studio");
    expect(safeStudioDestination("//attacker.test/studio")).toBe("/studio");
    expect(safeStudioDestination("/studio/../account")).toBe("/studio");
    expect(safeStudioDestination("/studio/dev-access?next=/studio")).toBe("/studio");
    expect(safeStudioDestination("/studio/login")).toBe("/studio");
  });

  it("encodes a safe return path for the local bootstrap route", () => {
    expect(studioDevelopmentAccessPath("/studio/movies?state=draft")).toBe(
      "/studio/dev-access?next=%2Fstudio%2Fmovies%3Fstate%3Ddraft",
    );
  });
});
