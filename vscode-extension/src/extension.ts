import * as vscode from 'vscode';
import * as path from 'path';
import * as fs from 'fs';
import { execFile } from 'child_process';
import { promisify } from 'util';

const execFileAsync = promisify(execFile);

// ---- Resolve analyzer command ----

function getAnalyzerCommand(): { cmd: string; prefixArgs: string[] } {
    const config = vscode.workspace.getConfiguration('twigAnalyzer');

    // Strategy 1: Use configured pythonPath
    const configured = config.get<string>('pythonPath', '');
    if (configured) {
        return { cmd: configured, prefixArgs: ['-m', 'twig_analyzer'] };
    }

    // The extension is installed at: ~/.vscode-server/extensions/twig-static-analyzer/
    // (or ~/.vscode/extensions/... on desktop)
    // The twig_analyzer Python package is copied inside the extension dir.
    const extDir = path.resolve(__dirname, '..');

    // Strategy 2: Python package inside extension dir
    const extVenvPython = path.join(extDir, '..', '..', '..', '..', '..', 'symfony-twig', '.venv', 'bin', 'python3');
    if (fs.existsSync(extVenvPython)) {
        return { cmd: extVenvPython, prefixArgs: ['-m', 'twig_analyzer'] };
    }

    // Strategy 3: Look for symfony-twig/.venv in HOME
    const homeDir = process.env.HOME || '/home/rlawjddn';
    const homeVenvPython = path.join(homeDir, 'symfony-twig', '.venv', 'bin', 'python3');
    if (fs.existsSync(homeVenvPython)) {
        return { cmd: homeVenvPython, prefixArgs: ['-m', 'twig_analyzer'] };
    }

    // Strategy 4: Try twig-analyze CLI on PATH
    return { cmd: 'twig-analyze', prefixArgs: [] };
}

// ---- LSP-compatible types (matches twig_analyzer.diagnostics output) ----

interface LspPosition {
    line: number;      // 0-indexed
    character: number; // 0-indexed
}

interface LspRange {
    start: LspPosition;
    end: LspPosition;
}

interface LspDiagnostic {
    message: string;
    severity: number;  // 1=Error, 2=Warning, 3=Info, 4=Hint
    range: LspRange;
    code: string;
    source: string;
}

interface AnalyzerOutput {
    files: Record<string, LspDiagnostic[]>;
    diagnostics: LspDiagnostic[];
    summary: {
        total: number;
        errors: number;
        warnings: number;
        info: number;
        hints: number;
    };
}

// ---- Diagnostics Collection ----

const diagnosticCollection = vscode.languages.createDiagnosticCollection('twig-analyzer');

// ---- Extension Activation ----

export function activate(context: vscode.ExtensionContext) {
    console.log('Twig Static Analyzer is now active');

    // Register command: manual analysis
    const analyzeCmd = vscode.commands.registerCommand('twig-analyzer.analyze', () => {
        const editor = vscode.window.activeTextEditor;
        if (editor) {
            analyzeDocument(editor.document);
        }
    });
    context.subscriptions.push(analyzeCmd);

    // Watch for file changes
    const config = vscode.workspace.getConfiguration('twigAnalyzer');

    if (config.get<boolean>('runOnOpen', true)) {
        // Analyze currently open files on activation
        vscode.window.visibleTextEditors.forEach(editor => {
            if (isTwigFile(editor.document)) {
                analyzeDocument(editor.document);
            }
        });
    }

    // Analyze on file open
    context.subscriptions.push(
        vscode.window.onDidChangeActiveTextEditor(editor => {
            if (editor && config.get<boolean>('runOnOpen', true)) {
                if (isTwigFile(editor.document)) {
                    analyzeDocument(editor.document);
                }
            }
        })
    );

    // Analyze on save
    context.subscriptions.push(
        vscode.workspace.onDidSaveTextDocument(document => {
            if (config.get<boolean>('runOnSave', true)) {
                if (isTwigFile(document)) {
                    analyzeDocument(document);
                }
            }
        })
    );

    // Analyze on change (debounced)
    let changeTimer: NodeJS.Timeout | undefined;
    context.subscriptions.push(
        vscode.workspace.onDidChangeTextDocument(event => {
            if (config.get<boolean>('runOnSave', true)) {
                return; // Only run on save
            }
            if (!isTwigFile(event.document)) {
                return;
            }
            if (changeTimer) {
                clearTimeout(changeTimer);
            }
            changeTimer = setTimeout(() => {
                analyzeDocument(event.document);
            }, 1000);
        })
    );

    // Clean up on close
    context.subscriptions.push(
        vscode.workspace.onDidCloseTextDocument(document => {
            diagnosticCollection.delete(document.uri);
        })
    );

    // Status bar item
    const statusBarItem = vscode.window.createStatusBarItem(
        vscode.StatusBarAlignment.Right, 100
    );
    statusBarItem.command = 'twig-analyzer.analyze';
    statusBarItem.text = '$(check) Twig';
    statusBarItem.tooltip = 'Twig Static Analyzer';
    statusBarItem.show();
    context.subscriptions.push(statusBarItem);
}

export function deactivate() {
    diagnosticCollection.clear();
}

// ---- Core Logic ----

function isTwigFile(document: vscode.TextDocument): boolean {
    const config = vscode.workspace.getConfiguration('twigAnalyzer');
    const extensions: string[] = config.get('fileExtensions', ['.twig', '.html.twig']);

    if (document.languageId === 'twig') {
        return true;
    }

    // Check file extensions
    for (const ext of extensions) {
        if (document.fileName.endsWith(ext)) {
            return true;
        }
    }

    return false;
}

async function analyzeDocument(document: vscode.TextDocument): Promise<void> {
    const config = vscode.workspace.getConfiguration('twigAnalyzer');

    if (!config.get<boolean>('enabled', true)) {
        diagnosticCollection.delete(document.uri);
        return;
    }

    try {
        const filePath = document.uri.fsPath;
        const analyzerArgs = buildAnalyzerArgs();
        const commonArgs = [...analyzerArgs, '--format', 'json', filePath];

        const execOptions = {
            timeout: 30000,
            maxBuffer: 10 * 1024 * 1024,
            env: { ...process.env, PYTHONUNBUFFERED: '1' },
        };

        const { cmd, prefixArgs } = getAnalyzerCommand();
        const allArgs = [...prefixArgs, ...commonArgs];

        console.log(`[twig-analyzer] Running: ${cmd} ${allArgs.join(' ')}`);

        let stdout = '';
        let stderr = '';

        try {
            const result = await execFileAsync(cmd, allArgs, execOptions);
            stdout = result.stdout;
            stderr = result.stderr;
        } catch (err1: any) {
            // Fallback: try 'twig-analyze' CLI directly
            try {
                const result = await execFileAsync('twig-analyze', commonArgs, execOptions);
                stdout = result.stdout;
                stderr = result.stderr;
            } catch (err2: any) {
                if (err2.code === 'ENOENT') {
                    vscode.window.showWarningMessage(
                        'Twig Static Analyzer: Python analyzer not found. ' +
                        'Run: bash ./vscode-extension/install.sh from the symfony-twig directory'
                    );
                } else if (err2.killed) {
                    console.warn('[twig-analyzer] Timed out');
                } else {
                    console.error('[twig-analyzer] Error:', err2.message || err2);
                }
                return;
            }
        }

        if (stderr && stderr.trim()) {
            console.warn('twig-analyzer stderr:', stderr);
        }

        const output: AnalyzerOutput = JSON.parse(stdout);
        const fileDiags = output.files[filePath];

        if (fileDiags) {
            const vsDiags: vscode.Diagnostic[] = fileDiags.map(d =>
                lspToVsCodeDiagnostic(d, document)
            );
            diagnosticCollection.set(document.uri, vsDiags);
        } else {
            diagnosticCollection.delete(document.uri);
        }

    } catch (err: any) {
        console.error('Twig analyzer error:', err.message || err);
    }
}

function buildAnalyzerArgs(): string[] {
    const config = vscode.workspace.getConfiguration('twigAnalyzer');
    const args: string[] = [];

    // Disabled rules
    const disabledRules: string[] = config.get('disabledRules', []);
    if (disabledRules.length > 0) {
        args.push('--disable', disabledRules.join(','));
    }

    // Severity overrides
    const severityOverrides: Record<string, string> = config.get('severityOverrides', {});
    for (const [ruleId, severity] of Object.entries(severityOverrides)) {
        args.push('--severity', `${ruleId}=${severity}`);
    }

    return args;
}

function lspToVsCodeDiagnostic(
    lspDiag: LspDiagnostic,
    document: vscode.TextDocument
): vscode.Diagnostic {
    // Convert LSP severity to VS Code severity
    const severityMap: Record<number, vscode.DiagnosticSeverity> = {
        1: vscode.DiagnosticSeverity.Error,
        2: vscode.DiagnosticSeverity.Warning,
        3: vscode.DiagnosticSeverity.Information,
        4: vscode.DiagnosticSeverity.Hint,
    };

    const range = new vscode.Range(
        new vscode.Position(lspDiag.range.start.line, lspDiag.range.start.character),
        new vscode.Position(lspDiag.range.end.line, lspDiag.range.end.character)
    );

    const diag = new vscode.Diagnostic(
        range,
        lspDiag.message,
        severityMap[lspDiag.severity] || vscode.DiagnosticSeverity.Warning
    );

    diag.source = lspDiag.source || 'twig-analyzer';
    diag.code = lspDiag.code;

    return diag;
}
