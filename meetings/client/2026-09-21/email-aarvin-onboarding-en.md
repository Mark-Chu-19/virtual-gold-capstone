# Onboarding email from Aarvin George

| | |
|---|---|
| **From** | Aarvin George (`aarvin.george.p98@gmail.com`) — Virtual Gold alumnus / BG developer, Pittsburgh |
| **To** | Mark Chu |
| **Received** | After the 2026-09-21 client meeting, before 2026-09-24 (exact date not recorded) |
| **Context** | Aarvin was introduced at the 2026-09-21 client meeting (`notes-gemini-en.pdf`) as the developer of the enterprise assistant, currently designated VG08 / "BG assistant 08". He is the technical counterpart for the HTTP endpoint integration. |
| **Status** | Reply outstanding. Three deliverables requested; hardware answer asked for "this week". |

## What this email settles

It converts the 2026-09-21 decision (horizontal first, framed as a chief-of-staff assistant, standalone HTTP service) into a concrete specification, and adds three things the meeting notes do not contain:

1. **The end user is a C-suite executive.** Data is that executive's day-to-day email and documents — not an IT department, not customer service.
2. **The core difficulty is defined as contextual judgement**, with two named examples: a personal phone number vs a public support number, and names quoted inside email threads.
3. **The local model is to make those judgements and output a confidence score.** This is a design instruction, and it runs against the conclusion of our own security research (`docs/research/`, presented 2026-09-21): contextual sensitivity has a ~48% human inter-annotator agreement ceiling, so that research recommends minimising model judgement rather than scoring it. See `docs/architecture/horizontal-draft/sanitization-gate-options-zh.html` for both architectures side by side.

## Open questions this email raises

- **Does the API contract carry provenance?** Whether the endpoint receives a flat block of text or text tagged with its source decides which architecture is even possible. Aarvin promised an initial API contract on 2026-09-22 (meeting notes); confirm whether it has arrived.
- **Where do 100 annotated emails come from?** A C-suite executive's real mailbox is almost certainly unavailable to us. If the baseline is synthetic, the annotation ground truth needs a defensible basis.
- **Does the OCR link imply scanned documents and attachments are in scope?** That would be a material scope addition.
- **Workstream overlap.** His five areas map onto our five owners (set 2026-09-18), but Mark lands on both Service Engineering and Coordination, and Zhexuan lands on both Evaluation and Model Work.

---

## Original text

> Hi Mark,
>
> Good to be working with you on this. A few things before we meet again so our next call can focus on the first viable prototype.
>
> **Project Overview**
>
> You are building a service that strips private data from text before it is sent to a cloud AI model. It will run locally on an open-source model using your own hardware. Our system calls it automatically before text reaches an AI assistant used daily by a c-suite executive.
>
> Determining what counts as private is the main challenge. Context matters—for instance, a personal phone number vs. a public support number, or names quoted in email threads. Because no rigid rule covers every case, the local model needs to make these judgments and output a confidence score.
>
> **Team Roles & Workstreams**
>
> There are five main areas of responsibility:
>
> 1. Evaluation & Test Data: Creating standard benchmark examples and leading evaluation metrics.
> 2. Privacy Research: Defining personal data boundaries and regulatory requirements.
> 3. Model Work: Prompting, configuring the local model, and generating confidence scores.
> 4. Service Engineering: Building a fast, reliable local service and handling failure modes.
> 5. Integration & Coordination: Managing documentation, progress updates, and the final demo.
>
> **Action Items Before We Meet**
>
> 1. Start Evaluation Early: One person should immediately create a baseline dataset. Take 100 realistic emails, manually annotate what should be redacted, and use this to score model updates throughout the semester.
> 2. Designate a Lead Contact: Choose one person as the primary point of contact for all communication with us.
> 3. Assess Hardware: Confirm what hardware you have access to, specifically GPUs (personal or university-provided). Running local models on standard CPUs takes significantly longer, which impacts design decisions. Please confirm your hardware setup this week.
>
> **AI Usage Guidelines**
>
> Feel free to use AI tools for code, research, and drafting. We only ask that you review all generated content thoroughly. Ensure your documentation is clear, precise, and well-edited so your work is represented effectively. If you are planning to send over AI-generated documentation,, be sure that it is easily digestible and carries real signal
>
> **Next Steps**
>
> Please send back:
>
> - Each team member's top two preferred areas, one non-preferred area, and estimated weekly availability.
> - Your designated primary contact.
> - Summary of available hardware.
>
> If you would like relevant background reading before our meeting, this resource is recommended: Google whitepaper on agent interactions: https://www.kaggle.com/whitepaper-agent-tools-and-interoperability, unlimited OCR by Baidu L https://github.com/baidu/Unlimited-OCR, how to use AI for secure document processing: https://www.mindstudio.ai/blog/ai-secure-document-processing-local-models-pii-detection
>
> I will send over the full specification once role assignments are confirmed.
>
> Feel free to let me know if you have any concerns
>
> Best regards,
> Aarvin George

*Transcribed verbatim, including the original's double comma in the AI Usage Guidelines paragraph and the stray "L" in the OCR link. Links not opened or verified.*
