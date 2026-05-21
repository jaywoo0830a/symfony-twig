import * as vscode from 'vscode';
import { execFile } from 'child_process';
import { promisify } from 'util';

const execFileAsync = promisify(execFile);

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

        // Try multiple execution strategies in order
        let stdout = '';
        let stderr = '';

        // Strategy 1: twig-analyze CLI (installed via pip)
        try {
            const result = await execFileAsync('twig-analyze', commonArgs, execOptions);
            stdout = result.stdout;
            stderr = result.stderr;
        } catch {
            // Strategy 2: python3 -m twig_analyzer
            try {
                const python = config.get<string>('pythonPath', 'python3');
                const result = await execFileAsync(python, ['-m', 'twig_analyzer', ...commonArgs], execOptions);
                stdout = result.stdout;
                stderr = result.stderr;
            } catch (err2: any) {
                if (err2.code === 'ENOENT') {
                    vscode.window.showWarningMessage(
                        'Twig Static Analyzer: twig-analyze not found. ' +
                        'Run: bash ./vscode-extension/install.sh'
                    );
                } else if (err2.killed) {
                    console.warn('Twig analyzer timed out');
                } else {
                    console.error('Twig analyzer error:', err2.message || err2);
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
