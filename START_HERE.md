# Your first walkthrough

You already have a working offline prototype. Start by opening the generated `report.html` under `runs/`.

1. **Inspect three cases.** Find a monitored order, an escalated order, and a no-action order. Read their reasons. Explain what evidence made each decision possible.
2. **Change a business rule.** Run the same sample with a lower automatic-action value limit:

   ```sh
   python3 triage.py --csv "$HOME/Downloads/DataCoSupplyChainDataset.csv" --limit 200 --max-auto-value 200
   ```

   Compare the new report with the default report. Why did some orders move to human review?

3. **Read one audit record.** In `decisions.jsonl`, see how the evidence, proposal, final action, policy version, and reason fit together. This is the accountability part of bounded autonomy.
4. **Understand the current limit.** Offline mode is a rule-based simulation. Historical replay uses outcomes already recorded. Neither is a tested live AI agent or an early-warning predictor.
5. **Enable the real agent.** Follow the README's API setup. Run five synthetic orders first. We can inspect its tool calls, proposals, and policy overrides together.
6. **Publish to your GitHub account.** Sign in locally with `gh auth login` or GitHub's website. Review the repository contents, choose a repository name and visibility, then publish the source and synthetic examples. Keep the original CSV, `runs/`, and secrets out of Git.

## A concise interview explanation

“I built a logistics triage prototype to explore bounded autonomy. It aggregates line items into orders, applies explicit limits on automatic actions, escalates uncertain cases, and records each decision. The offline replay tests the policy boundaries. An optional OpenAI Agents SDK integration uses tools to inspect evidence and policy, with application code retaining decision authority. The current experiment is retrospective, so the next step is evaluation with time-correct snapshots and expert-labelled cases.”

Only describe the optional integration as tested with a live model after you have actually run and reviewed it.
