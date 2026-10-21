# Phase 2 — One-question-at-a-time format

Use only when empty slots remain after Phase 1. One message = one slot. Ask in the user's language.

## Standard format

```
[Question] {slot name in user-friendly words}

Options:
  1) {option A} — {one line on when it fits}
  2) {option B} — {one line on when it fits}
  3) Enter it directly

Recommended: {default} ({why this is the default})
```

## Rules

- **One message = one slot.** Never ask about 2 or more slots in one message.
- If a technical term appears, add a **one-line explanation** with it (H5).
- When you get an answer, fill the slot and move **to the next empty slot**.
- If the user answers several slots at once, accept them all and re-check only the empty slots (H2).
- The AskUserQuestion tool shows options as a nice UI — prefer it when the environment supports it.

## Good / Bad examples

**Bad (3 questions in one message):**
> "Tell me the domain, the DNS service and your email."

→ Users usually answer only 1~2, or think "ugh, complicated" and answer carelessly. Once the agent starts guessing the missing information, things go off the rails.

**Good (one message = one slot):**
> "Which domain will you use? (e.g. `example.com`)"
> (after the answer)
> "Thanks. Where is your DNS managed?
>   1) Cloudflare
>   2) AWS Route53
>   3) Other (enter it directly)
>
> Recommended: Cloudflare (company default)"

---

**Bad (no explanation of a technical term):**
> "Enter your Let's Encrypt email."

**Good:**
> "Which email should receive Let's Encrypt certificate expiry notices? (No sign-up is needed; you only get a notice when expiry is near.)"

---

**Bad (asking again for information the user already gave):**
> User: "docker-compose has the port set to 3000"
> Agent: "Which port will you use?"

**Good:** stay silent and move to the next empty slot. (`port=3000` is already extracted)
