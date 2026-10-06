<!-- Doc 05 — Artifact, Memory, Tools (§17–21)
     Bagian dari societas-full-product-spec. Urutan dokumen diatur di README.md.
     Nomor section dipertahankan; referensi silang antar-doc memakai nomor section (#N, 5A.x, 72A.x). -->

# 17. Artifact System

Output agent tidak boleh hanya dianggap sebagai text response.

Artifact adalah output yang dapat dipakai agent lain.

Contoh:

```text
research.md
architecture.md
benchmark.json
diagram.svg
decision.md
patch.diff
pull-request.md
test-report.md
```

## 17.1 Contract-First Integration (Generate-First, Gate-Second, Prompt-Last)

Agen dilarang menulis fungsi fetch/call Web3 atau API dari nol secara manual. Alur serah terima backend/smart contract ke frontend:

1. **Pinning Kontrak:** task frontend wajib mengunci `contract_hash` (SHA256 dari OpenAPI spec / Contract ABI). Jika spec berubah, task ditandai **stale**.
2. **Codegen Otomatis:** Go runtime men-generate client TypeScript/Rust binding via CLI tool (`orval`, `wagmi` typegen, `viem`) sebelum agen bekerja.
3. **Strict Usage:** agen hanya boleh mengimpor dan memanggil fungsi hasil generate tersebut.
4. **Token-Saver Lookup:** agen tidak menerima seluruh spec OpenAPI/ABI ke prompt. Disediakan tool deterministik `contract.lookup(operation_id)` yang mengembalikan potongan spec relevan saja — tanpa vector search.

Artifact memiliki:

- ID
- owner
- creator
- task
- type
- path
- checksum
- created_at
- updated_at
- metadata

---

# 18. Artifact Flow

```text
Research Agent
      |
      v
research.md
      |
      v
CEO
      |
      v
architecture task
      |
      v
CTO
      |
      v
architecture.md
      |
      v
Engineer
      |
      v
code + tests
      |
      v
Reviewer
      |
      v
review.md
```

---

# 19. Memory System

Memory dibagi menjadi beberapa level dan disimpan sesuai sifatnya pada dua pilar penyimpanan (Dual-Storage Architecture, lihat #37):

- Data terstruktur/operasional (task state, run history, approval, akumulasi budget) -> **Operational Store** (SQLite)
- Representasi semantik (embedding artifact, ringkasan riset, koordinat memori masa lalu) -> **Cognitive Store** (Embedded Vector DB)

## 19.1 Agent Memory

Informasi khusus agent.

Contoh:

```text
CTO preferences
Engineering decisions
Technical context
Past reviews
```

## 19.2 Workspace Memory

Informasi seluruh organisasi.

Contoh:

```text
Architecture decisions
Project direction
Company rules
Important findings
```

## 19.3 Task Memory

Context yang hanya relevan terhadap satu task.

## 19.4 Run Memory

Context selama satu execution.

## 19.5 Memory Storage Mapping

Setiap level memory di atas di-map ke pilar penyimpanan:

- Agent Memory & Workspace Memory: entry terstruktur (sumber, timestamp, scope) di SQLite; isi naratifnya di-embed ke Vector DB agar dapat di-retrieve semantik.
- Task Memory: relasi task -> artifact/memory disimpan di SQLite; ringkasannya di-embed untuk retrieval.
- Run Memory: append-only di event log SQLite; tidak di-embed (ephemeral).

Retrieval semantik selalu melewati Vector DB dan mengembalikan ID referensi (5A.24) — bukan pencarian teks mentah di SQLite.

---

# 20. Memory Rules

Memory harus memiliki:

- source
- timestamp
- confidence
- scope
- owner

Jangan memasukkan semua chat ke memory secara otomatis.

Memory harus memiliki lifecycle.

Contoh:

```text
raw event
    |
    v
candidate memory
    |
    v
validated memory
    |
    v
persistent memory
```

---

# 21. Tools

Agent dapat memiliki tools.

Contoh:

```text
filesystem
shell
git
browser
search
http
database
terminal
python
docker
kubernetes
```

Tool access harus configurable per agent.

## 21.1 Tool Interface — MCP Client

Antarmuka tool agen menggunakan arsitektur **MCP Client**: Tool Runtime di backend Go bertindak sebagai client yang terhubung ke MCP server internal maupun eksternal (filesystem, shell, git, search, dst). Tool baru ditambahkan dengan mendaftarkan server MCP — bukan mengubah kode agen. Permission tetap di-gate deterministik oleh Policy Engine (#22) sebelum call diteruskan ke MCP server.

---
