# ChatGPT Sites access experiment

A private, synthetic-data-only compatibility test for using ChatGPT Sites as Pebble Hood's host. The existing Python backend is unchanged.

- `probe/` is the published Site source. Its hosting manifest retains the exact Sites project ID. The Site contains a static test page and a JSON marker; it has no Robinhood integration or secrets.
- `phone-probe/` is a separate **Sites Test** watch app, with its own UUID. It tests phone-side HTTPS requests without a Sites service credential. It also provides a settings link for normal ChatGPT browser sign-in and a follow-up cookie-sharing test. It does not replace Hood Demo.
- `../docs/sites-access-probe.json` records actual HTTP results and the physical-phone test status.
- `../docs/sites-test.md` explains the results, their limits and reproduction.

The Site is kept owner-private. Native Sites source credentials were used only in session memory for the private source repository; no token is in this directory, the PBW, GitHub, or deployment assets. The documented local Sites source helper was absent from this execution environment and unavailable as a skill resource. Source synchronization used standard Git with transient in-memory HTTP authentication, verified the pushed HEAD, and packaged only `.openai/hosting.json` plus `dist/` for the native private deployment call.
