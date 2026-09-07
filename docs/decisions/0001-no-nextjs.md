# 0001 — Vite + React + TanStack Router, not Next.js or TanStack Start

**Date:** 2026-09-08 · **Status:** accepted

## Context

The frontend is an agent console and an admin dashboard, both entirely behind a
login, plus a small embeddable customer chat widget. The backend is FastAPI
(Python). The first draft of the plan specified Next.js 15.

## Decision

Build a client-rendered SPA with Vite, React 19, TanStack Router and TanStack
Query. FastAPI serves the built static files in production; Vite proxies `/api`
in development.

## Reasoning

Next.js's value is its server: SSR, server components, server actions, route
handlers, caching. This application has no use for any of it — no SEO, no public
pages, no first-paint requirement, and all state is live and authenticated.
Adopting it would mean running a Node process whose only job is to render a shell
and proxy to Python, reasoning about which half of each component tree runs where,
and deploying two runtimes instead of one.

TanStack Start v1 is stable and well built, but it is also a full-stack framework
— the same server capability we just established is unnecessary. Picking it would
repeat the mistake with a newer logo.

TanStack Router earns its place on its own merits: end-to-end typed routes and
typed *search params*. The ticket queue and dashboard are mostly filter state
(`?status=escalated&priority=P1&channel=whatsapp`), and having that validated and
typed rather than stringly-typed `URLSearchParams` is a direct fit. Shareable
filtered views come free, which the agent console wants.

## Consequences

- One server runtime (Python), one build artifact (static files).
- No SSR available. If a public marketing site or SEO-visible customer pages are
  ever needed, they are a separate project, not a refactor of this one.
- Smaller community answer pool than Next.js for framework-level questions;
  acceptable, since the framework surface here is small.
