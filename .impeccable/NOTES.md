# Why the detector ignores these paths

(Moved out of config.json, where no tool read them.)

- **legacyJinjaLayer**: templates/** and static/style.css are the frozen legacy Jinja look (Chakra Petch, dark/red). Since 9 Oct 2026 only the guest project page, the sign-in fallback and the error page remain. DESIGN.md scopes them out; they are not reviewed against it. Remove these ignores when the guest pages retire.

- **scratchpadDocs**: Session scratchpad holds standalone documents (plans, audit reports) published as artifacts. They borrow Odin's palette and typeface on purpose but are documents, not the product UI — DESIGN.md's type ramp and radius scale describe app components and do not apply to them.
