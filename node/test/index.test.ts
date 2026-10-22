import { describe, expect, it } from "vitest";
import * as sdk from "../src/index";

describe("@fastn-ai/sdk", () => {
  it("exposes the default base URL", () => {
    expect(sdk.DEFAULT_BASE_URL).toBe("https://connect.fastn.dev");
  });
});
