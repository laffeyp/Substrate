# Security

Report suspected vulnerabilities privately via GitHub security advisories ("Report a
vulnerability" on the Security tab). Please don't open a public issue for one.

Two facts worth knowing:

- A run record is data. Reading, replaying, or diffing a record from anywhere runs
  nothing; blob references inside it are validated before use (`record/blobstore.py`).
- Loading a topology module (`--topology-module`) executes its Python, like running
  any script. Only load modules you trust.
