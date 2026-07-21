# Literary Production Loop Design

## Goal

Improve the existing vendor-neutral three-role workflow so that formal prose
spends its context budget on character, action, social friction, and language
rather than reproducing the control plane's audit reasoning.

The workflow remains:

`Writer -> Blind Reader -> Chapter Editor -> optional Patch Writer -> re-review`

No provider, model, Agent product, or native session implementation becomes a
core dependency.

## Design

The full scene package remains the editor-facing control plane. It may contain
falsification checks, cognition alternatives, causal responsibility, and
professional-risk analysis. The Writer handoff receives a derived story brief
containing only scene boundaries, active pressure, character states, beat
obligations, information budget, character breath, and aftermath. Editor-only
reasoning sections are not copied into the capsule.

Compiled role tasks are added for planning, Blind Reader, and Chapter Editor.
They are vendor-neutral and carry execution intent rather than model choices:
planning may use high reasoning; prose and default reviews use medium. The
Chapter Editor receives a bounded machine-diagnostics summary and must perform
the complete five-dimension review on every round. It may not limit a re-review
to confirming that the previous finding disappeared.

Patch instructions include the finding's location, prose evidence, reader
effect, and revision intent. The Patch Writer must make the smallest causally
complete change, distribute necessary motivation through action or interaction,
and avoid translating review language into an explanatory paragraph.

## Cost Boundary

The default call count remains unchanged: one planning call, one draft call,
two review calls, and only when MUST findings exist, one patch call followed by
two full re-reviews. No extra default reviewer is introduced. Blind Reader
still receives prose only. Machine diagnostics are bounded and sent only to the
Chapter Editor.

## Verification

Tests prove that editor-only scene sections are absent from Writer handoffs,
compiled prompts remain vendor-neutral, review tasks cover transcript dialogue,
analytical spill, generic competence, repair seams, and genuine reader desire,
Patch Writer receives evidence-aware directives, and the Chapter Editor gets
bounded machine diagnostics without contaminating Blind Reader context.
