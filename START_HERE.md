# Your first walkthrough

You have a working offline prototype and have completed live AI smoke tests on five and ten synthetic orders; see EVALUATION.md. Start by opening the generated `report.html` under `runs/`.

1. **Inspect three cases.** Find a monitored order, an escalated order, and a no-action order. Read their reasons. Explain what evidence made each decision possible.
2. **Change a business rule.** Run the same sample with a lower automatic-action value limit:

   ```sh
   python3 triage.py --csv "$HOME/Downloads/DataCoSupplyChainDataset.csv" --limit 200 --max-auto-value 200
   ```

   Compare the new report with the default report. Why did some orders move to human review?

3. **Read one audit record.** In `decisions.jsonl`, see how the evidence, proposal, final action, policy version, and reason fit together. This is the accountability part of bounded autonomy.
4. **Understand the current limit.** Offline mode is a rule-based simulation. Historical replay uses outcomes already recorded. Live mode has also been tested on synthetic orders, but neither mode predicts delays in advance or follows up on shipments.
5. **Enable the real agent.** Follow the README's API setup. Run five synthetic orders first. Inspect its saved proposals, final actions and agent error fields together. Detailed tool-call traces are not currently saved.
6. **Keep the published project accurate.** The source and synthetic examples have been published to GitHub. Review future changes before publishing them, and keep the original CSV, `runs/`, and secrets out of Git. The next functional extension is a simulated active-shipment case with fresh tracking updates and scheduled rechecks.

## A concise interview explanation

“I built a logistics triage prototype to explore bounded autonomy. It aggregates line items into orders, applies explicit limits on automatic actions, escalates uncertain cases, and records each decision. The offline replay tests the policy boundaries. I also ran the OpenAI Agents SDK integration with a live model on ten distinct synthetic orders. It uses tools to inspect evidence and policy, with application code retaining decision authority. The current experiment is retrospective, so the next step is evaluation with time-correct snapshots and expert-labelled cases.”

Describe the live runs as basic tests on synthetic orders, not a real-world effectiveness evaluation.
