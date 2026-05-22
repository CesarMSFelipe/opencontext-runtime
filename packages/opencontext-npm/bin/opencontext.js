#!/usr/bin/env node
const { spawn } = require("child_process");
const { resolve } = require("path");

const PIPX_BIN = process.env.PIPX_BIN_DIR
  ? `${process.env.PIPX_BIN_DIR}/opencontext`
  : "opencontext";

const args = process.argv.slice(2);
spawn(PIPX_BIN, args, { stdio: "inherit", env: process.env }).on(
  "exit",
  (code) => process.exit(code ?? 1),
);
