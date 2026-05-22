#!/usr/bin/env node
const { execSync } = require("child_process");

try {
  execSync("pipx install opencontext-cli", { stdio: "inherit" });
} catch {
  console.warn(
    "Could not install opencontext-cli via pipx. " +
      "Make sure pipx is installed (brew install pipx). " +
      "You can also install manually: pip install opencontext-cli",
  );
}
