# Paper Orchestra Frontend

From the repository root, after following the local setup in the main README:

```bash
./scripts/run-local.sh
```

Open <http://127.0.0.1:8501>. The UI opens before keys are configured, and reports
missing generation prerequisites in the sidebar. Restart after changing `.env`.
The default OpenAI pipeline requires `OPENAI_API_KEY`, with no Gemini key.
Figure generation uses OpenAI-produced matplotlib code for both plots and diagrams.
Email notifications are optional and require SMTP configuration.

Use **Load CVPR Example** to populate the input materials. Choose **No** for
figure generation to use its supplied figure. Generated files and logs are saved
under `demo_logs/` inside the repository.

The frontend launches `paper_writing_cli.py` as a background process. Keep the
server running until it finishes. Stopping the server can leave a pipeline running;
use `pgrep -fl paper_writing_cli.py` to identify it and `kill <PID>` to stop that
specific process.
