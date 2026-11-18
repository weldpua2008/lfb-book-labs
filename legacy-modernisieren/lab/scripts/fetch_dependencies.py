#!/usr/bin/env python3
"""Download the official pinned JDBC artifact; never silently accept another version."""
import hashlib,pathlib,urllib.request
ROOT=pathlib.Path(__file__).resolve().parents[1]
URL="https://jdbc.postgresql.org/download/postgresql-42.7.14.jar"
SHA256="73914527305a40cce504b0d3d90b23caf565136912d607ae8ae7c5895512332c"
target=ROOT/"lib/postgresql-42.7.14.jar"
if target.exists():
 data=target.read_bytes()
 if hashlib.sha256(data).hexdigest()!=SHA256:raise SystemExit("Existing JDBC artifact has wrong SHA-256; inspect it before rebuilding.")
 print("pgJDBC42.7.14 cached; SHA-256 verified")
else:
 with urllib.request.urlopen(URL,timeout=60) as response:data=response.read()
 if hashlib.sha256(data).hexdigest()!=SHA256:raise SystemExit("Official download differs from pinned SHA-256; no build performed.")
 target.parent.mkdir(exist_ok=True);target.write_bytes(data)
 print("pgJDBC42.7.14 downloaded from official origin; SHA-256 verified")
