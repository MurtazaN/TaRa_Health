---
name: structured-responses
description: Formatting and language rules for responses to the user — conclusion first, then bullets, numbered lists or tables, never paragraph blocks; every technical term defined at first use; complete sentences; no contractions. Use this skill for essentially every response, and load it whenever you are about to write more than two sentences of prose. It applies to explanations, status reports, findings, comparisons, plans, option lists, and answers to "what is X" questions. The user has explicitly rejected essay-style answers, so treat prose as the exception that needs justifying rather than the default.
---

# Structured responses

## Why this exists

A response gets read to find one thing and act on it: a decision, a number, a next step. Two failures follow from writing prose instead:

1. **The load-bearing sentence hides.** Put a decision inside a paragraph and it sits at the same visual weight as the sentences supporting it. The reader cannot find it again later, even having read it once.
2. **Undefined terms stall the reader.** A term used as though it were shared knowledge forces the reader to either stop and ask, or nod along without understanding. Both waste the exchange.

Structure moves the work of organising from the reader to the writer, where it costs far less. Bolding does not substitute for it — a bolded sentence buried mid-paragraph is still buried, which is the specific failure that produced this skill.

## The default shape

Every response follows the same order:

1. **The answer or conclusion**, in the first line.
2. **The support for it**, beneath, as structured items.
3. **What happens next**, if anything is owed.

Never make the reader reach the end to learn what the point was.

## Response flow

The default shape above fixes where the conclusion sits. The rules below fix the
order of everything beneath it. They exist because a response can satisfy every
formatting and language rule in this file and still be unreadable, purely from
the order in which its parts arrive.

### One issue occupies one top-level section, and its parts are subsections

A response presents one issue at a time and finishes each issue before starting
the next. **One issue gets exactly one top-level number.** A top-level number is a
promise that a new subject has started, so splitting a single issue across
several of them tells the reader there are several issues.

The parts of an issue are **subsections with their own headings**, not an
invisible checklist and not a fixed template. They are numbered `4.1`, `4.2` and
so on beneath the issue's own number, so that any part can be cited directly.

### How many subsections an issue earns

Seven subsections exist. **How many appear scales with the issue.** A large or
critical issue earns all seven; a small or medium one needs only what it is and
how to fix it. Include each subsection when its question is live for the reader:

| # | Subsection | Include it when |
|---|---|---|
| 1 | What the issue is | Always. This is the floor, and on its own it is a complete answer for a small issue |
| 2 | The evidence | The reader could reasonably doubt the issue is real, or it was found rather than reported |
| 3 | Why it matters | The consequence is not obvious from the description |
| 4 | An example | The issue is a behaviour rather than a fact — something that happens, rather than something that is |
| 5 | The remedies | More than one is worth considering |
| 6 | The cost of each remedy | Subsection 5 is present. A remedy without its cost is a recommendation in disguise |
| 7 | The recommendation | Subsection 5 is present |

**A heading is a promise that something worth reading follows.** Printing a
heading for a question the reader does not have is worse than omitting it, so do
not pad a small issue up to seven subsections. Equally, do not compress a
critical one down: if the reader must choose between remedies, subsections 5, 6
and 7 are not optional.

When only subsections 1 and 5 are live, they need no headings at all — a short
issue is a paragraph naming it and a sentence giving the fix.

Two consequences follow, and both are absolute:

1. **A solution must never appear before the issue it solves.** A reader who
   meets a fix first has to hold it in mind while hunting for what it repairs.
2. **A new issue must never appear after the solutions have started.** Once a
   remedy has been given, every issue raised afterwards makes the reader re-open
   the question of whether that remedy still covers it.

Where several issues share one cause, explain the cause once, before the first
remedy, rather than repeating it per issue. Where two issues share evidence,
state the shared evidence once as background before the issues begin: identical
evidence appearing as the primary proof of two different claims reads as either
one issue repeated or a fact that changed in between.

**This rule outranks answering in the order asked.** Follow the asked order by
default, because it is usually also the readable order; depart from it when a
later item supplies the reason an earlier one turned out the way it did.

### Every section states its own purpose in its first line

The first line of a section says what the section is about and why it appears in
this response. Tables, code blocks, command output and evidence come after that
line, never before it. A heading is not a substitute: a heading is a label, and a
label cannot say why the reader should spend time on what follows.

The cost is one sentence per section, which is redundant whenever the heading is
already explicit. Accept the redundancy — the alternative is a reader deciding
section by section whether reading it was worth the time.

## Formatting rules

- **Label every section, every subsection, every list item and every table row.** A heading reads `## 1. Findings`, and its subsections read `### 1.1 What broke`. This is not decoration: it is what lets the reader say "answer 3.2" instead of describing the passage they mean, and it is the difference between a reply that can be navigated and one that has to be re-read. Unlabelled headings are how a decision became unfindable once already.
- **Any label scheme works, as long as it is consistent and every item carries one.** Arabic numerals (`1.`, `2.`), capital letters (`A.`, `B.`), lower-case letters (`a.`, `b.`) and Roman numerals (`i.`, `ii.`) are all acceptable. Mixing schemes across depth levels is encouraged, because it makes a reference such as "2.B.iii" unambiguous. What is never acceptable is an item with no label at all.
- **Number every row of every table**, in a leading column, so a row can be cited as "row 3" instead of quoted back in full.
- **Use numbered lists** when order, count, or sequence matters, so items can be referred to by number later.
- **Use bullets** when the items are peers and order does not matter. Give each bullet a label even so.
- **Use tables** when comparing three or more things across two or more dimensions.
- **Use headings** whenever a response covers more than one topic.
- **Keep one idea per item.** An item carrying two ideas should be two items.
- **Convert any run of three or more consecutive sentences** into structured items. That run is the signal that prose has crept back in.

## Heading and reference rules

- **Every heading must be plain English and must be readable on its own**, by someone who has not read the rest of the response. `## 3. The messaging fix this implies` fails, because "this" points at something the reader has to go and find.
- **Never refer to an earlier numbered item as though the number were its name.** `## 3. Preview size — deviation 3.A fixed half of it` is unreadable: "deviation 3.A" names a location, not a subject. Restate the subject in words every time it is raised.
- **When an item is finished and needs no decision from the reader, say so in its first line, and do not give it a table of choices.** A table of choices is a request for a decision. Attaching one to completed work tells the reader they owe an answer when they do not.
- **Name every choice by the change it makes and the effect that change has.** A column or heading reading `Options` forces the reader to decode every cell before knowing what is on offer. Write `Change` and `Effect` columns instead, or name the option in its first three words.

## Language rules

- **Define every technical term at first use**, in one sentence, before using it in an argument. A term the reader has not been given cannot carry an argument for them.
- **Industry jargon is welcome, but it must arrive quoted and explained.** The reader wants to learn the professional vocabulary, so do not translate it away into plain words. Put the jargon term in quotes and define it in the same sentence: `A "pong" is the server's one-word reply to a client's "keep-alive" (is this connection still open?) check.` Both halves are required — quotes alone leave the reader guessing, and an explanation without quotes hides which word was the term of art. This applies to every jargon term in a response, not only the first few, and a glossary section at the top does not excuse a new term introduced further down.
- **Label every identifier with the kind of thing it is.** An identifier is any name lifted out of the code or configuration: a function, a module, a file, a class, a variable, a setting, a column, an endpoint, an environment variable. Write "the `_evict` function", "the `ws_manager.py` module", "the `SEND_TIMEOUT_SECONDS` setting" — never the bare name on its own. Without the descriptor the reader cannot tell whether `_evict` is something that runs, something that is read, or somewhere that code lives, and the sentence stalls exactly where it should carry meaning.
- **A defect in code is a "bug" or an "issue", never a "problem".** The word "problem" is reserved for difficulties that are not defects — a constraint, an obstacle, a question without a good answer. Keeping the two apart means "issue" always points at something in the codebase and "problem" never does, so the reader knows which they are reading about from the noun alone.
- **Use one word per concept, fixed before you use it.** When a response sorts items into classes — defect against gap, blocker against nice-to-have, confirmed against unresolved — state what each class means before the first item, then never relabel an item. Calling the same item a "defect" in its heading and a "gap" in its body tells the reader the classification is decorative.
- **Never use a pronoun whose referent is not named in the same sentence. Write the noun instead.** "Three of the four endpoints must not call it" hands the reader a pronoun and a search; "three of the four endpoints must not call `ensure_participant`" hands them the meaning on first read. The rule covers `it`, `this`, `that`, `these`, `those`, `the former`, `the latter`, `the above` and `the same`. Repeating a long noun is always cheaper than making the reader scroll back for it.
- **Write each item as a complete sentence.** Telegraphic fragments look organised while communicating less — `tsbuildinfo stale — dist empty — exit 0` is three nouns and a reader who has to guess the causal link.
- **Avoid contractions and casual filler.** Write "do not" rather than "don't".
- **Bold the load-bearing phrase** in a long item, so a scanning reader lands on it. This supplements structure and never replaces it.

## Exemptions

Two, and only two:

1. **Code blocks, file contents, commit messages and pull-request bodies** keep their own conventions. Bulleting a commit message or a source file breaks the format it has to conform to.
2. **One-line factual answers stay one line.** "Yes, all tests pass." and "Line 42." need no structure. Imposing a bullet on a three-word answer adds ceremony without clarity.

**Explaining a single term is not an exemption.** A definition is exactly where the reader is least able to follow connected prose, because the terms it depends on are the ones they do not have yet. Structure it: what it is, then what it does, then why it matters here.

## Before and after

Three real failures, each with its correction.

**Example 1 — a decision the reader could not find.**

Before:
> …so the fix I would propose is that **before writing, I give you the complete file list with every non-obvious setting named, and write nothing until you say go.** That will produce more back-and-forth than today; say if you want it looser.

After:
> **The rule I propose:**
> 1. Before writing any file, I give you a manifest of every file and every non-obvious setting.
> 2. I write nothing until you approve it.
> 3. This produces more back-and-forth. Say if it is too tight.

**Example 2 — terms used without definition.**

Before:
> `incremental: true` made `nest build` silently produce nothing, because tsc writes `tsconfig.build.tsbuildinfo` outside `outDir`, so `deleteOutDir` wiped `dist` while the buildinfo claimed everything was emitted.

After:
> **The build silently produced no output.** The terms involved:
> - **`outDir`** — the folder compiled JavaScript is written to, here `dist`.
> - **`incremental`** — a setting that makes the compiler skip work it believes is already done.
> - **`tsbuildinfo`** — the file recording what it believes is already done.
>
> **The failure:** the record file was written outside `dist`, so deleting `dist` did not delete the record. The compiler then read a record claiming the work was complete and emitted nothing.

**Example 3 — an explanation padded into an essay.**

Before: a thirty-five line comment block narrating an investigation.

After: what the setting does, and the one consequence of removing it. Investigation notes belong in a change log or nowhere.

**Example 4 — jargon unquoted and unexplained, identifiers unlabelled.**

Before:
> Every send in `ws_manager` has a deadline. The pong reply does not, so once `_evict` closes a socket the fan-out stalls.

After:
> Every outbound write performed by the connection registry in the `app/services/ws_manager.py` module has a time limit. The "pong" — the server's one-word reply to a client's "keep-alive" (is this connection still open?) check — has none. So once the `_evict` function closes a socket, the "fan-out" (the loop that pushes one message out to every recipient) stops making progress.

## Self-check before sending

Run through these, and fix what fails:

- [ ] Is the conclusion in the first line?
- [ ] Does each issue occupy exactly one top-level section, with its parts as subsections beneath it?
- [ ] Does each issue carry the subsections whose questions are live for the reader — no padding on a small issue, no missing remedies or costs on a critical one?
- [ ] Does any solution appear before the issue it solves, or any issue appear after the solutions have started?
- [ ] Is any code defect called a "problem" rather than a "bug" or an "issue"?
- [ ] Does every section state what it is about and why it is here, before its first table or code block?
- [ ] Is there any run of three or more sentences without structure?
- [ ] Is every technical term defined at first use?
- [ ] Is every piece of industry jargon both quoted and explained, including the ones introduced late in the response?
- [ ] Does every identifier carry the kind of thing it is — "the `x` function", "the `y.py` module" — rather than standing bare?
- [ ] Is every classifying word ("defect", "gap", "blocker") defined before first use and applied to the same item consistently throughout?
- [ ] Does every `it`, `this`, `that` and `the latter` have its referent named in the same sentence?
- [ ] Could the reader find the decision without reading everything?
- [ ] Is every item a complete sentence?
- [ ] Are contractions and casual filler gone?
- [ ] Does every section, subsection, list item and table row carry a label?
- [ ] Does every heading read as plain English, without pointing at another item by its number?
- [ ] Is any completed item wrongly presented with a table of choices?
- [ ] Is every choice named by the change it makes and the effect that change has?
