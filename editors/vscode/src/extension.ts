/**
 * The VS Code client for the FastPDLC language server.
 *
 * There is deliberately no validation, no graph and no diagnostics logic in this
 * file. All of that is `fastpdlc lsp`, which is the same Python that CI runs — an
 * extension that re-implemented any of it in TypeScript would be a second judge, and
 * an editor that says green while the gate says PAC-020 is worse than no editor
 * support at all. So this starts a process, points it at the workspace, and gets out
 * of the way.
 *
 * The one thing it owns is telling you, in words, when the server is not installed.
 */
import * as path from 'path';
import * as vscode from 'vscode';
import {
  LanguageClient,
  LanguageClientOptions,
  ServerOptions,
  TransportKind,
} from 'vscode-languageclient/node';

let client: LanguageClient | undefined;

function settings() {
  return vscode.workspace.getConfiguration('fastpdlc');
}

/** Build the argv for `fastpdlc lsp`. Global flags precede the subcommand. */
function serverArgs(): string[] {
  const config = settings().get<string>('config', 'product.config.yaml');
  const plugin = settings().get<string>('plugin', '');
  const args: string[] = ['-c', config];
  if (plugin) {
    args.push('-p', plugin);
  }
  args.push('lsp');
  return args;
}

async function start(): Promise<void> {
  if (!settings().get<boolean>('enable', true)) {
    return;
  }
  const folder = vscode.workspace.workspaceFolders?.[0];
  if (!folder) {
    return;
  }

  const command = settings().get<string>('path', 'fastpdlc');
  const server: ServerOptions = {
    command,
    args: serverArgs(),
    transport: TransportKind.stdio,
    options: { cwd: folder.uri.fsPath },
  };

  // Scoped to markdown under the configured product directory's repo. The server
  // decides what it recognises; a document it does not know simply gets no answers.
  const clientOptions: LanguageClientOptions = {
    documentSelector: [{ scheme: 'file', language: 'markdown' }],
    synchronize: {
      fileEvents: vscode.workspace.createFileSystemWatcher(
        new vscode.RelativePattern(folder, '**/product.config.yaml'),
      ),
    },
    outputChannelName: 'FastPDLC',
  };

  client = new LanguageClient('fastpdlc', 'FastPDLC', server, clientOptions);

  try {
    await client.start();
  } catch (err) {
    client = undefined;
    const install = 'Show install command';
    const choice = await vscode.window.showErrorMessage(
      `FastPDLC: could not start "${command}". Is it installed and on PATH?`,
      install,
    );
    if (choice === install) {
      const channel = vscode.window.createOutputChannel('FastPDLC');
      channel.appendLine('The language server ships as an extra on the Python package:');
      channel.appendLine('');
      channel.appendLine("    pip install 'fastpdlc[lsp]'");
      channel.appendLine('');
      channel.appendLine('If it lives in a virtualenv, set fastpdlc.path to that');
      channel.appendLine(`absolute path, e.g. ${path.join('.venv', 'bin', 'fastpdlc')}`);
      channel.appendLine(`(${path.join('.venv', 'Scripts', 'fastpdlc.exe')} on Windows).`);
      channel.appendLine('');
      channel.appendLine(String(err));
      channel.show();
    }
  }
}

async function stop(): Promise<void> {
  await client?.stop();
  client = undefined;
}

export async function activate(context: vscode.ExtensionContext): Promise<void> {
  context.subscriptions.push(
    vscode.commands.registerCommand('fastpdlc.restart', async () => {
      await stop();
      await start();
    }),
    vscode.workspace.onDidChangeConfiguration(async (event) => {
      if (event.affectsConfiguration('fastpdlc')) {
        await stop();
        await start();
      }
    }),
  );
  await start();
}

export async function deactivate(): Promise<void> {
  await stop();
}
