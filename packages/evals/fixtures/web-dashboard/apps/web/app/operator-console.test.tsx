import { modeLabel } from "../lib/api";

if (modeLabel({ local_record_mode: true, github_mode: "missing_credentials" }) !== "Local record mode") {
  throw new Error("Expected local record mode label");
}

