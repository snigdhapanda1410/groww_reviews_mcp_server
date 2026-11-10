# 📊 Groww Reviews MCP — Project Problem Statement

> **Created:** 2026-11-01 | **Platform:** Groww (Stocks, Mutual Fund, IPO)
> **App:** [Groww on Google Play](https://play.google.com/store/apps/details?id=com.nextbillion.groww&hl=en_IN)

---

## 🎯 Goal

Turn raw mobile-store feedback into a **weekly pulse** your team can scan in minutes:
- What users care about
- What they actually said (verbatim)
- What to do next (concrete action ideas)

Reviews are already public. The job is to **aggregate → theme → summarize → deliver** that insight through familiar surfaces — **Google Docs** for the written pulse and **Gmail** for a draft you can send yourself — without handling credentials or REST wiring manually.

---

## 🔄 End-to-End Flow

```
Pull Reviews  ──►  Cluster into Themes  ──►  Generate Weekly Pulse
     │                                               │
     │                                               ▼
Play Store (public)                          Google Doc (written note)
                                                     │
                                                     ▼
                                             Gmail Draft (email to self)
```

1. **Pull** recent App Store / Play Store reviews for Groww (public exports only, last 8–12 weeks).
2. **Cluster** them into a small set of themes (≤ 5) — e.g., onboarding, KYC, payments, statements, withdrawals.
3. **Distill** a one-page weekly note highlighting the top 3 themes.
4. **Publish** that note to **Google Docs** where stakeholders can read it.
5. **Draft** an email via **Gmail** containing or linking to that pulse.

---

## 📦 Deliverables

### Weekly One-Page Pulse
| Section | Requirement |
|---|---|
| **Top Themes** | What people are talking about most (top 3 of ≤5 clusters) |
| **Real User Quotes** | 3 verbatim snippets from reviews — no invented wording |
| **Action Ideas** | 3 concrete next steps grounded in the themes |

### Email Draft
Send yourself (or an alias) a draft email containing this weekly note or a clear pointer to it.

---

## 👥 Who This Helps

| Audience | Why |
|---|---|
| **Product / Growth** | Prioritize fixes and improvements from real signals |
| **Support** | Align messaging with what users are actually saying |
| **Leadership** | One-page health check without drowning in raw reviews |

---

## 🏗️ What You Must Build

| # | Task |
|---|---|
| 1 | Import reviews from the last **8–12 weeks** (fields: rating, title, text, date — whatever the export provides) |
| 2 | Group reviews into **at most 5 themes** (e.g., onboarding, KYC, payments, statements, withdrawals) |
| 3 | Generate a weekly one-page note: **top 3 themes + 3 user quotes + 3 action ideas** |
| 4 | Draft an email with the note to yourself or an alias |

---

## ⚙️ Integrations — Google Docs & Gmail via MCP

> [!IMPORTANT]
> Use **MCP (Model Context Protocol) servers** for Google Docs and Gmail — **not** bespoke OAuth + REST client code.

- MCP servers expose tools your agent/app can call for creating/updating the pulse document and creating the draft message.
- This keeps Docs and Gmail consistent with the course tooling and avoids duplicating auth and HTTP plumbing.
- Choose MCP servers or connectors your environment provides for Docs and Gmail.
- **Requirement: MCP-first**, not "call Google APIs manually."

---

## 🚧 Key Constraints

| Constraint | Rule |
|---|---|
| **Reviews** | Public review exports only — no scraping behind store logins or ToS-violating automation |
| **Themes** | Maximum **5 themes** for clustering; written pulse highlights the **top 3** |
| **Length** | Keep the note scannable — **≤ 250 words** where applicable |
| **Privacy** | No PII — no usernames, emails, device IDs, or other identifiable reviewer data in any artifact; quotes must be anonymous / stripped |

---

## 📁 Project Structure

```
c:\Projects\Grow reviwes_MCP\
├── docs\
│   ├── problemstatement.txt   ← original brief
│   └── problemstatement.md   ← this file (structured context)
```

---

## 🗒️ Notes

- The Groww Play Store link: `https://play.google.com/store/apps/details?id=com.nextbillion.groww&hl=en_IN`
- The product covers **Stocks, Mutual Funds, and IPOs** — themes should reflect these verticals where relevant.
- The weekly cadence implies this pipeline should be repeatable / schedulable.

