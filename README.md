# Societas — Full Product Specification (Split Edition)

Dokumen spesifikasi dipecah menjadi 10 file agar mudah direvisi per topik.
**Urutan section tetap sama persis dengan dokumen asli** — nomor section tidak berubah,
jadi referensi silang (`#48`, `5A.8`, `72A.5`, `I3`, dst) tetap valid antar-dokumen.

## Aturan Revisi

- Revisi dilakukan di file topik terkait, bukan di dokumen gabungan.
- Nomor section **jangan diubah** — referensi silang antar-file bergantung padanya.
- Jika menambah section baru, gunakan nomor desimal di sebelah section induk
  (mis. `5A.28`, `60.3`) agar urutan tetap terbaca.
- **Section 72A (Doc 10) adalah Source of Truth** untuk schema, event, dan invariants —
  jika ada konflik dengan doc lain, 72A yang berlaku.

## Peta Dokumen

| File | Section | Topik |
|------|---------|-------|
| `01-vision-and-core.md` | 1–5 | Visi, prinsip produk, masalah, konsep inti (workspace, agent, role) |
| `02-ai-control-plane.md` | 5A.1–5A.27 | Control Plane: orchestrator, budget, context, router (Jev), policy, intake pipeline (§7.1 dirujuk dari sini) |
| `03-tasks-and-lifecycle.md` | 6–9 | Agent lifecycle, task system, intake & routing pipeline (§7.1), task graph, delegation |
| `04-communication-and-events.md` | 10–16 | Communication model, event model/bus, message categories, streaming, agent conversation |
| `05-artifacts-memory-tools.md` | 17–21 | Artifact system & contract-first (§17.1), artifact flow, memory system, tools + MCP client |
| `06-permissions-approvals-roles.md` | 22–32 | Permission & path jailing, approval & risk tier, autonomy, peran agent, role customization (declarative squad), model provider, cost tracking + OpenRouter accounting |
| `07-dashboard-config-storage.md` | 33–37 | Dashboard (task board, approval center), workspace.yaml (risk, toolchain, escalation_lead), dual-storage SQLite + Vector DB |
| `08-runtime-architecture.md` | 38–56 | Suggested architecture, module, agent runtime (step function), event bus (outbox, mailbox), retry, parallelism, conflict resolution (escalation_lead), voice/multimodal, channel taxonomy, backpressure, retention |
| `09-security-sandbox-observability.md` | 57–72 | Security model, secrets, tool sandbox & OS-level isolation, git integration & worktree, MCP search, structured tool calls, observability/logging/tracing, agent run, replay, context budget, protocol versioning |
| `10-contracts-mvp-roadmap.md` | 72A–105 | **Source of Truth**: invariants I1–I15, envelope, core schemas (task, artifact, budget), state machine, event registry, payload schemas, error catalog, alur baku, MVP, roadmap, priorities, killer demo, anti-boncos |

## Titik Panas Revisi Terakhir (quick lookup)

- Dual-Storage: Doc 05 (§19.5), Doc 07 (§37)
- 2x Rebuttals & escalation_lead: Doc 02 (5A.2), Doc 06 (§30.1), Doc 07 (§36), Doc 08 (§48)
- Deterministic Guard & OS Isolation: Doc 06 (§22), Doc 09 (§59)
- Risk Tier & Runtime Escalation: Doc 06 (§23.1), Doc 10 (72A.5), Doc 02 (5A.8)
- Dynamic Context Assembly: Doc 02 (5A.4), Doc 07 (§36)
- Task Pause/Resume & Step Function: Doc 06 (§23), Doc 07 (§33.3), Doc 08 (§40), Doc 10 (72A.5–72A.7)
- MCP Client & Search: Doc 05 (§21.1), Doc 09 (§62–63)
- Toolchain Runner & Compiler Gate: Doc 02 (5A.21), Doc 07 (§36 toolchain), Doc 09 (§60.2)
- Contract-First (codegen, contract.lookup): Doc 05 (§17.1), Doc 10 (72A.5 `contract_hash`)
- OpenRouter Usage Accounting: Doc 06 (§32.1), Doc 02 (5A.10, 5A.25)
- Dynamic Enum Injection & Blind Delegation: Doc 02 (5A.8), Doc 06 (§30.1), Doc 10 (72A.8, 72A.10)
- Search & Replace Edit + Serial Merge Queue: Doc 09 (§60.3–60.4), Doc 06 (§28), Doc 08 (§45)
- PROJECT_MAP auto-regen: Doc 03 (§7.1), Doc 09 (§60.4)
- Provider Rate Limiter (RPM/TPM token bucket): Doc 02 (5A.8)
- Memory Curation / anti Zombie Memory: Doc 05 (§19.6, §20), Doc 07 (§37.3), Doc 02 (5A.24)
