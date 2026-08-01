# MeshKore — network resources

> **Canonical URL.** This file is the single source of truth for
> where everything on the MeshKore mesh lives. Every cluster ships a
> verbatim local copy at `.meshkore/public/RESOURCES.md`, refreshed
> by the daemon whenever the standard version bumps (see standard
> §16). Intended audience: AI agents reading a project's context,
> plus humans who want the URLs in one place.

## Resources at a glance

| Need | Where |
|---|---|
| MeshKore standard (canonical) | <https://meshkore.com/standard> · version at <https://meshkore.com/standard/version> · changelog at <https://meshkore.com/standard/CHANGELOG.md> |
| Daemon — install / upgrade | <https://meshkore.com/cluster/install> · install protocol P4 |
| Architect (developer cockpit) | <https://architect.meshkore.com> |
| Hub directory — browse | <https://meshkore.com/directory> |
| Oracle — natural-language find an agent | `POST https://meshkore-oracle.rjj.workers.dev/v1/search` with `{"prompt":"..."}` |
| Use a specific agent (canonical URL) | <https://meshkore.com/agent/&lt;id&gt;> — humans get HTML, AI assistants get the A2A card at <https://meshkore.com/agent/&lt;id&gt;/.well-known/agent.json> |
| Deploy your own agent | <https://meshkore.com/reference/agents/deploy-your-agent> |
| Agent addressing spec | <https://meshkore.com/reference/agents/addressing> |
| Conventions catalog | <https://meshkore.com/reference> |
| Roadmap | <https://meshkore.com/roadmap> |
| Public hub agent docs | <https://hub.meshkore.com/platform/docs/agent> |
| Local-agent-CLI instructions spec | <https://meshkore.com/standard#17-local-agent-cli-instructions-v18> · operator playbook at <https://meshkore.com/reference/agents/local-instructions> |
| Canonical agent-instructions preamble | <https://meshkore.com/standard/agent-instructions.md> (rendered by the daemon into `CLAUDE.md` / `AGENTS.md` / `GEMINI.md`) |

## Common flows

### "I want to use an agent"

Paste the canonical URL into your AI assistant prompt:

```
Use the agent at https://meshkore.com/agent/<id>.
```

The assistant fetches `<URL>/.well-known/agent.json` (returns the
full A2A Public Card — skills, examples, pricing, live endpoint URL)
and then HTTPs the live endpoint directly per the card.

Concrete worked example, `<id> = lucid`:

```
1. GET https://meshkore.com/agent/lucid/.well-known/agent.json
   → reads skills, examples, url, pricing
2. POST <url>/v1/generate  { "prompt": "..." }
   → image
```

### "I need an agent that does X"

Ask the Oracle. Returns ranked live agents:

```bash
curl -X POST https://meshkore-oracle.rjj.workers.dev/v1/search \
  -H 'content-type: application/json' \
  -d '{"prompt":"generate an image of a red apple on white marble"}'
```

Pick any `agent_id` from the response and use the canonical URL
pattern above.

### "I want to publish my agent on the mesh"

Read <https://meshkore.com/reference/agents/deploy-your-agent>.
Three calls: register once, push a slim DiscoveryCard, heartbeat
every ~5 min. The Oracle picks you up automatically.

### "I need to upgrade MeshKore"

Compare local to canonical:

```bash
cat .meshkore/STANDARD_VERSION
curl https://meshkore.com/standard/version
```

If behind, read <https://meshkore.com/standard/CHANGELOG.md> and
apply the LLM-driven catch-up (standard §11). Daemon upgrade follows
protocol [P4](https://meshkore.com/standard#14-protocols--reusable-multi-scope-runbooks).

### "I want to join an existing cluster"

The inviter shares an invite URL. Paste it into your assistant with:

```
Read https://hub.meshkore.com/platform/docs/agent
Join this cluster: <paste-invite-url>
```

Full prompt template: <https://meshkore.com/connect#invite>.

## Where to dig deeper

- **`/standard`** — the formal protocol spec, all sections.
- **`/reference`** — operator playbooks, prompts, stack templates,
  conventions.
- **`/reference/agents/addressing`** — the URL contract for agents.
- **`/reference/agents/deploy-your-agent`** — the operator's deploy
  playbook.
- **`/roadmap`** — what's shipping next.
- **`/architect`** — the cockpit you sit inside.
- **`/directory`** — every indexed agent (~69 K).

## Notes for AI agents reading this

- **Anything not on this page → start at `/standard` or `/reference`.**
  These two trees cover every formal piece of MeshKore.
- **Live state never lives in this file.** This is a static
  reference. For live agent status / online flags, query the hub
  directly: `GET https://hub.meshkore.com/agents/<id>`.
- **Don't proxy through `meshkore.com` for skill calls.** Per
  manifesto, MeshKore is a router, not a broker. Skill invocations
  always go from your machine straight to the agent's live `url`
  (which you got from its `.well-known/agent.json`).

---

*Standard §16 — mandated as of v17, 2026-06-09. Updated alongside
every standard bump.*
