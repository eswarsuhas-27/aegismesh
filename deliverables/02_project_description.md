## Inspiration
When production breaks, the loudest error is rarely the cause. A database misconfiguration makes the gateway scream while the database is quiet. AI assistants make this worse by suggesting fixes nobody has validated. In a hospital the stakes are higher: restarting the wrong system, or "clearing a stuck queue", can delay medication or lose lab results. We wanted an AI that does not just explain an incident but proves a fix is safe and proves it worked.

## What it does
AegisMesh is an autonomous incident-response agent that works on a simulated environment (a cloud stack, or a synthetic hospital: EHR, lab, imaging, pharmacy, HL7 interface engine, bedside monitors). Given an incident it:
1. **Observes** logs, health, configuration and dependencies.
2. **Investigates** with competing root-cause hypotheses, each tied to log evidence.
3. **Researches** with Tavily. Every citation must carry a quote that is verified word for word against the retrieved page; anything unverifiable is downgraded and never influences the decision.
4. **Challenges** its own theories with a Skeptic agent that separates facts from assumptions.
5. **Plans** several candidate fixes, then **simulates each one** in a deterministic digital twin. Outcomes come from the simulator's rules, never from a model.
6. **Enforces safety** with a policy engine that never sees model text. It blocks destructive or disruptive actions (for example purging queued clinical messages, or restarting life-critical systems without a human).
7. **Executes** only a safe, working action and **verifies recovery from the simulator's real state**, comparing prediction with observation.
8. If no safe action can fix it (the monitor-gateway case), it applies the safest mitigation, asks for human approval, and says so. It never overrides policy.

The dashboard shows service health, a dependency graph, timeline, hypotheses with confidence, Tavily sources, every candidate with predicted vs simulated result and policy verdict, clinical impact (hospital mode), the verified outcome, live API usage, and recorded evaluation results.

## How we built it
- **Nebius Token Factory + NVIDIA Nemotron** power four agents (Investigator, Researcher, Skeptic, Planner) through the OpenAI-compatible API. Models are right-sized per task: a small Nemotron for query writing and evidence extraction, a mid-size one for investigation and planning, and the largest available for the Skeptic. Model ids are discovered at runtime and only NVIDIA models are ever selected. If Token Factory fails mid-run the system degrades to a deterministic planner and says so.
- **Strict validation of every model output:** invented log ids, services, sources and actions are dropped and logged; actions are parsed into the simulator's grammar before policy sees them.
- **Tavily used efficiently:** at most two queries per incident, near-duplicate queries dropped, basic search depth with three results, every answer cached to disk, a hard credit budget, and an adaptive mode that skips research when the logs already settle the question. Vendor-style scenarios (real-looking SQLSTATE, Redis, JVM, DICOM and OpenSSL errors with no config-change hint) are where research earns its cost.
- **Evaluation harness:** reproducible incidents with known root causes, run as baseline vs AI vs AI+research, reporting root-cause accuracy, recovery, blocked unsafe actions, Tavily searches and billed credits. See RESULTS.md for the recorded numbers.
- Standard library only (no dependencies), 39 automated tests, a hosted demo with a spending cap and free replay of real recorded runs.

## Challenges
Models hallucinate citations, so we made the quote check mandatory. Safety cannot depend on the model being well behaved, so policy judges the simulated outcome instead of model text, and our tests feed it deliberately malicious model output. Honest measurement meant admitting small samples and simple scenarios instead of claiming big wins.

## Accomplishments
A complete loop from detection to verified recovery, a hospital mode where patient safety changes the decisions, a bad-model test suite proving unsafe or invented output cannot cause harm, and an evaluation that reports Tavily's measured contribution, whatever it is.

## What we learned
Counterfactual testing changes what an AI agent can be trusted to do. Research is worth its credits only when the logs are ambiguous, so gating it adaptively is both cheaper and more honest. Prediction and verification must stay separate.

## What's next
Richer twins imported from real topology and runbooks, more incident families, human-approval workflows for protected systems, and larger evaluation sets.

*Simulation only. Synthetic data, no patient identifiers. Not a medical device and not clinical advice.*
