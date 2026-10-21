# Anti-patterns — doing this means failure

Refer to this when the agent is stuck or tempted. Failure patterns that come up again and again, with the right alternative.

## Procedure

| ❌ Wrong approach | ✅ Right approach |
|--------------|--------------|
| "This skill is simple, so write it right away without design" | Never skip Phase 0 brainstorming, even if short — the simpler a skill looks, the higher the risk of unexamined assumptions |
| Presenting a single option in Phase 0 | 2~3 approaches + why one is recommended, so the user sees alternatives and chooses |
| "Build it first and add things as needed" (scope grows unchecked) | Fix the boundary in one line in Phase 0 Step D: "does X but not Y" (YAGNI) |
| Ignoring a similar existing skill and building a new one | Search existing skills in Phase 0 Step E → decide extend/separate/replace |
| Starting to write SKILL.md before the Phase 0 agreement | HARD GATE — disk writes start in Phase 3. Once sunk cost appears, the wrong scope sets in |
| Cramming everything into one action (`do-all`) or over-splitting (`get-a`, `get-a-b`, `get-a-b-c`) | Rough action design in Phase 0 Step F — one clear purpose each |
| Open-ended questions that make the user dig for answers | Multiple choice (offer options) whenever possible — open-ended only for creative design |
| Presenting a long design all at once | Confirm per section: "Is this right so far?" (incremental validation) |
| Fixing out-of-scope problems on the fly during IMPROVE | Record as "related problem found" → suggest it to the user separately after the current patch |
| Passing the 8-principle checklist in your head only | In Phase 4, re-read SKILL.md with `Read` and fill in the checklist |
| Asking again for information the user gave | Extract in Phase 1 → confirm with only a one-line intent summary |
| Asking "domain and port and email" in one message | One message = one slot |
| Assuming no phase can be skipped | If Phase 1 fills everything, skipping Phase 2 is OK |
| Declaring the work done before the user says "OK" | Phase 6 exit condition = explicit user approval |
| Handling a review request in CREATE mode | Branch to REVIEW in §1 mode detection |

## Writing

| ❌ | ✅ |
|---|---|
| Baking in a real domain/IP/employee ID (e.g. `username@company-domain`) | A placeholder like `{user_email}` |
| A per-user PEM path in the SKILL.md body | Move it into `config.json.example` |
| Enforcing rules with only `MUST`, `NEVER`, `ALWAYS` | Add a one-line `(reason: ~)` next to the rule — say why |
| A single 600-line SKILL.md | A 300-line body + split into references/ |
| Vague UI directions like "check it" | "DSM → Control Panel → External Access → DDNS tab → Hostname column" |
| A pitfalls section full of generic warnings | Only problems actually encountered, briefly (better to drop unverified ones) |

## Scripts

| ❌ | ✅ |
|---|---|
| Making the agent write a new Python script on every skill call | Bundle shared logic in `scripts/` |
| Requiring external dependencies like `requests`, `httpx` | Use only the stdlib, such as `urllib` (for network-restricted environments) |
| Leaving non-ASCII text (e.g. Korean) garbled in the Windows console | Insert `sys.stdout.reconfigure(encoding="utf-8")` at the top |
| Throwing HTTP errors only as raw responses | Parse into a structured error dict + suggest the next action |
| Failing hard on an in-house self-signed SSL certificate | Allow opt-out through a `verify_ssl` setting |

## Conversation

| ❌ | ✅ |
|---|---|
| User says "push to master" and you just run it (but the branch is R) | Detect the mismatch → reconfirm "Are you sure it is master?" |
| After an action succeeds, print only "done" and stop | Offer 2~3 natural follow-up actions as options |
| Asking questions only as plain text without AskUserQuestion | Use the AskUserQuestion tool for an options UI when possible |
| Re-running a destructive command the user allowed once, without asking again | Reconfirm every time (force push, reset --hard, etc.) |

## Mode detection (REVIEW/IMPROVE additions)

| ❌ | ✅ |
|---|---|
| Hearing "review it" and starting to CREATE a new skill | §1 mode detection → enter REVIEW |
| Listing review issues without severity | Classify as 🟥/🟨/🟩 to show priority |
| Applying review results without user agreement | Ask "How much should I apply?" in Phase 4 |
| Saying "done" after an improvement without checking behavior | Call it for real in IMPROVE Phase 3 (when possible) |
