import * as vscode from 'vscode';
import {
    LanguageClient,
    LanguageClientOptions,
    ServerOptions
} from 'vscode-languageclient/node';

let client: LanguageClient;

export function activate(context: vscode.ExtensionContext) {
    // Command to start the Python Language Server
    const serverOptions: ServerOptions = {
        run: { command: 'rflow', args: ['lsp'] },
        debug: { command: 'rflow', args: ['lsp'] }
    };

    // Options to control the language client
    const clientOptions: LanguageClientOptions = {
        documentSelector: [{ scheme: 'file', language: 'resource-flow' }],
    };

    client = new LanguageClient(
        'resourceFlowLsp',
        'Resource Flow Language Server',
        serverOptions,
        clientOptions
    );

    // Start the client. This will also launch the server
    client.start();
}

export function deactivate(): Thenable<void> | undefined {
    if (!client) {
        return undefined;
    }
    return client.stop();
}
