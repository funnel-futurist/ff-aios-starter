# Run a terminal command Claude gives you

**What it's for:** sometimes Claude needs you to run a command yourself, for example a sign-in that opens your browser. This is how, in under a minute.

## The quickest way: inside Claude Code
1. In the Claude Code prompt, type `!` as the very first character. The prompt switches to shell mode.
2. Paste the command after it, for example `! gh auth login`, and press **Enter**.
3. The output appears in the conversation, and Claude can read it and carry on. To leave shell mode, press **Esc**, or **Backspace** on an empty prompt.

## In a terminal window
- **Mac:** press **Cmd + Space**, type `Terminal`, press **Enter**. Paste the command with **Cmd + V**, then press **Enter**.
- **Windows:** press the **Windows** key, type `PowerShell`, press **Enter**. Paste with **Ctrl + V**, then press **Enter**.
- Run it in the right folder: if Claude says "in your workspace", type `cd ` (with a space), drag the workspace folder onto the window, and press **Enter** before you paste.

## It worked when
The command finishes and the prompt comes back. A browser page opening, or a line saying "Logged in" or "Done", is usual.

## Send back
The last few lines of output, or "done". If the output contains a token, password or key, **don't paste it**: say "done, it printed a token" instead.

## Before you run anything
- Only run commands from your own Claude session or a person you trust. Don't run commands you found in an email or a stranger's message.
- If a command asks for a password or a payment, stop and ask why.

## Video and checks
- **Video: still to find.** On 2026-10-01 no transcript could be checked, because YouTube refused the requests. Per the `human_step` rule, the steps stand on the docs until a checked video is added.
- **Steps checked against:** Claude Code Docs, "Interactive mode", section "Shell mode with ! prefix" (https://code.claude.com/docs/en/interactive-mode), read 2026-10-01.
