from pygls.lsp.server import LanguageServer
from lsprotocol.types import (
    TEXT_DOCUMENT_DID_OPEN,
    TEXT_DOCUMENT_DID_CHANGE,
    TEXT_DOCUMENT_COMPLETION,
    Diagnostic,
    Range,
    Position,
    DiagnosticSeverity,
    CompletionItem,
    CompletionItemKind,
    CompletionList,
    PublishDiagnosticsParams,
)
from lark.exceptions import UnexpectedInput
import re
import urllib.parse
import os

from resource_flow.parser import RecipeParser

server = LanguageServer("resource-flow-server", "v0.1")

def _uri_to_path(uri: str) -> str:
    parsed = urllib.parse.urlparse(uri)
    path = urllib.parse.unquote(parsed.path)
    if os.name == 'nt' and path.startswith('/'):
        path = path[1:]
    return path

def _validate(ls, params):
    # ls.show_message_log(f"Validating {params.text_document.uri}")
    document = ls.workspace.get_text_document(params.text_document.uri)
    source = document.source
    
    diagnostics = []
    
    parser = RecipeParser()
    try:
        file_path = _uri_to_path(params.text_document.uri)
        parser.parse_string(source, file_path)
    except UnexpectedInput as e:
        line_num = getattr(e, 'line', None)
        col_num = getattr(e, 'column', None)
        
        # UnexpectedEOF gives line=-1, column=-1 in some Lark versions
        if line_num is not None and line_num > 0:
            line = line_num - 1
        else:
            line = max(0, len(source.splitlines()) - 1)
            
        if col_num is not None and col_num > 0:
            col = col_num - 1
        else:
            col = max(0, len(source.splitlines()[-1]) if source.splitlines() else 0)
            
        d = Diagnostic(
            range=Range(
                start=Position(line=line, character=col),
                end=Position(line=line, character=col + 1)
            ),
            message=str(e).split('\n')[0],
            severity=DiagnosticSeverity.Error
        )
        diagnostics.append(d)
    except ValueError as e:
        # Catch our custom semantic errors like macros already defined
        # We don't have line numbers for these right now easily, so put at 0,0
        d = Diagnostic(
            range=Range(
                start=Position(line=0, character=0),
                end=Position(line=0, character=1)
            ),
            message=str(e),
            severity=DiagnosticSeverity.Error
        )
        diagnostics.append(d)
    except Exception as e:
        pass
        
    ls.text_document_publish_diagnostics(
        PublishDiagnosticsParams(uri=params.text_document.uri, diagnostics=diagnostics)
    )

@server.feature(TEXT_DOCUMENT_DID_OPEN)
def did_open(ls, params):
    _validate(ls, params)

@server.feature(TEXT_DOCUMENT_DID_CHANGE)
def did_change(ls, params):
    _validate(ls, params)

@server.feature(TEXT_DOCUMENT_COMPLETION)
def completions(ls, params):
    document = ls.workspace.get_text_document(params.text_document.uri)
    source = document.source
    
    def_regex = re.compile(r'\bdef\s+((?:[0-9.]+\s+)?[a-zA-Z]+(?:\s+[a-zA-Z0-9_]+)*)')
    let_regex = re.compile(r'\blet\s+([a-zA-Z0-9_]+)')
    
    items = []
    
    for match in def_regex.finditer(source):
        name_part = match.group(1).split()[-1] 
        pass

    res_regex = re.compile(r'\bdef\s+(?:[0-9.]+\s+)?[a-zA-Z]+\s+([a-zA-Z0-9_]+)')
    
    keywords = {"def", "let", "mod", "use", "with", "using", "make", "min", "max", "basic", "cost", "time", "any", "cheapest", "fastest"}
    words = re.findall(r'[a-zA-Z_][a-zA-Z0-9_]*', source)
    
    unique_words = set(words) - keywords
    
    for kw in keywords:
        items.append(CompletionItem(
            label=kw,
            kind=CompletionItemKind.Keyword
        ))
        
    for word in unique_words:
        items.append(CompletionItem(
            label=word,
            kind=CompletionItemKind.Variable
        ))
        
    return CompletionList(is_incomplete=False, items=items)

def main():
    server.start_io()

if __name__ == "__main__":
    main()