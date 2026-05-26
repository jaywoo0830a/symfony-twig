import * as vscode from 'vscode';
import * as path from 'path';
import * as fs from 'fs';
import { execFile } from 'child_process';
import { promisify } from 'util';

const execFileAsync = promisify(execFile);
import { CliCommand } from './extension';
import { findAnalyzerCommand } from './extension';
import { isTwigFile, isInsideTwigTag, isInsideHtmlTag } from './extension';

// 9. Formatting provider
// ═══════════════════════════════════════════════════════════════════════

export class TwigFormattingProvider implements vscode.DocumentFormattingEditProvider {
    async provideDocumentFormattingEdits(
        document: vscode.TextDocument,
        _options: vscode.FormattingOptions,
        _token: vscode.CancellationToken,
    ): Promise<vscode.TextEdit[]> {
        const cmd = findAnalyzerCommand();
        const formatted = await this.formatWithCli(cmd, document);

        if (formatted === undefined) return [];

        const fullRange = new vscode.Range(
            document.positionAt(0),
            document.positionAt(document.getText().length),
        );
        return [vscode.TextEdit.replace(fullRange, formatted)];
    }

    private async formatWithCli(
        cmd: CliCommand,
        document: vscode.TextDocument,
    ): Promise<string | undefined> {
        const tmp = require('os').tmpdir();
        const tmpFile = require('path').join(tmp, `twig-fmt-${Date.now()}.twig`);

        try {
            require('fs').writeFileSync(tmpFile, document.getText(), 'utf-8');
            await execFileAsync(cmd.cmd, [...cmd.args, 'format', tmpFile], {
                timeout: 30000,
                env: cmd.env,
            });
            return require('fs').readFileSync(tmpFile, 'utf-8') as string;
        } catch {
            return undefined;
        } finally {
            try { require('fs').unlinkSync(tmpFile); } catch { /* ignore */ }
        }
    }
}

// ═══════════════════════════════════════════════════════════════════════
// 10. Hover provider — Twig built-in documentation
// ═══════════════════════════════════════════════════════════════════════

interface BuiltinEntry {
    readonly description: string;
    readonly since: string;
    readonly example: string;
    readonly link: string;
}

export const TWIG_DOCS = 'https://twig.symfony.com/doc/3.x';

export const BUILTIN_HOVER_DATA: Record<string, BuiltinEntry> = {
    // Tags
    apply:       { description: 'Applies a filter to a section of code',                               since: '1.0',  example: '{% apply upper %}Text{% endapply %}',                       link: `${TWIG_DOCS}/tags/apply.html` },
    autoescape:  { description: 'Controls auto-escaping strategy for a block',                          since: '1.0',  example: "{% autoescape 'html' %}...{% endautoescape %}",             link: `${TWIG_DOCS}/tags/autoescape.html` },
    block:       { description: 'Defines a block that child templates can override',                    since: '1.0',  example: '{% block title %}...{% endblock %}',                      link: `${TWIG_DOCS}/tags/block.html` },
    cache:       { description: 'Caches a template fragment',                                          since: '3.2',  example: '{% cache %}...{% endcache %}',                             link: `${TWIG_DOCS}/tags/cache.html` },
    deprecated:  { description: 'Marks a template section as deprecated',                              since: '1.36', example: "{% deprecated 'Use X instead' %}",                         link: `${TWIG_DOCS}/tags/deprecated.html` },
    do:          { description: 'Executes an expression without output',                               since: '1.0',  example: "{% do var = 'value' %}",                                  link: `${TWIG_DOCS}/tags/do.html` },
    embed:       { description: 'Embeds another template with block overrides',                        since: '1.8',  example: "{% embed 'template.twig' %}...{% endembed %}",             link: `${TWIG_DOCS}/tags/embed.html` },
    extends:     { description: 'Extends a parent template (must be the first tag)',                   since: '1.0',  example: "{% extends 'base.html.twig' %}",                          link: `${TWIG_DOCS}/tags/extends.html` },
    flush:       { description: 'Flushes the output buffer',                                           since: '1.5',  example: '{% flush %}',                                             link: `${TWIG_DOCS}/tags/flush.html` },
    for:         { description: 'Iterates over a sequence',                                           since: '1.0',  example: '{% for item in items %}...{% endfor %}',                  link: `${TWIG_DOCS}/tags/for.html` },
    from:        { description: 'Imports macro names from a template',                                since: '1.0',  example: "{% from 'macros.twig' import input %}",                   link: `${TWIG_DOCS}/tags/from.html` },
    guard:       { description: 'Conditionally outputs content based on a tag',                       since: '3.13', example: "{% guard function('route') %}...{% endguard %}",          link: `${TWIG_DOCS}/tags/guard.html` },
    if:          { description: 'Conditional block with elseif/else support',                         since: '1.0',  example: '{% if condition %}...{% endif %}',                       link: `${TWIG_DOCS}/tags/if.html` },
    import:      { description: 'Imports all macros from a template',                                 since: '1.0',  example: "{% import 'macros.twig' as macros %}",                    link: `${TWIG_DOCS}/tags/import.html` },
    include:     { description: 'Includes another template (use include() function instead)',          since: '1.0',  example: "{% include 'template.twig' %}",                          link: `${TWIG_DOCS}/tags/include.html` },
    macro:       { description: 'Defines a reusable macro',                                           since: '1.0',  example: '{% macro input(name, value) %}...{% endmacro %}',         link: `${TWIG_DOCS}/tags/macro.html` },
    sandbox:     { description: 'Enables sandbox mode for a block',                                   since: '1.0',  example: '{% sandbox %}...{% endsandbox %}',                        link: `${TWIG_DOCS}/tags/sandbox.html` },
    set:         { description: 'Assigns values to variables',                                        since: '1.0',  example: "{% set name = 'Fabien' %}",                               link: `${TWIG_DOCS}/tags/set.html` },
    use:         { description: 'Horizontal reuse — imports blocks from another template',            since: '1.0',  example: "{% use 'blocks.twig' %}",                                link: `${TWIG_DOCS}/tags/use.html` },
    verbatim:    { description: 'Outputs raw text without parsing Twig syntax',                       since: '1.0',  example: '{% verbatim %}...{% endverbatim %}',                      link: `${TWIG_DOCS}/tags/verbatim.html` },
    with:        { description: 'Creates a new inner scope with variables',                           since: '1.0',  example: "{% with {name: 'Fabien'} %}...{% endwith %}",              link: `${TWIG_DOCS}/tags/with.html` },
    types:       { description: 'Declares variable types for static analysis',                        since: '3.15', example: "{% types {name: 'string'} %}",                            link: `${TWIG_DOCS}/tags/types.html` },
    else:        { description: 'Default branch in if/for blocks',                                    since: '1.0',  example: '{% else %}',                                              link: `${TWIG_DOCS}/tags/if.html` },
    elseif:      { description: 'Conditional branch in if blocks',                                    since: '1.0',  example: '{% elseif condition %}',                                   link: `${TWIG_DOCS}/tags/if.html` },

    // Filters
    abs:         { description: 'Absolute value of a number',                                         since: '1.0',  example: '{{ -1|abs }}',                                             link: `${TWIG_DOCS}/filters/abs.html` },
    batch:       { description: 'Batches items into arrays of given size',                            since: '1.0',  example: '{{ items|batch(3) }}',                                      link: `${TWIG_DOCS}/filters/batch.html` },
    capitalize:  { description: 'Capitalizes the first character',                                    since: '1.0',  example: "{{ 'hello'|capitalize }}",                                  link: `${TWIG_DOCS}/filters/capitalize.html` },
    convert_encoding: { description: 'Converts string encoding',                                      since: '1.0',  example: "{{ data|convert_encoding('UTF-8', 'iso-2022-jp') }}",       link: `${TWIG_DOCS}/filters/convert_encoding.html` },
    date:        { description: 'Formats a date',                                                     since: '1.0',  example: "{{ post.publishedAt|date('Y-m-d') }}",                      link: `${TWIG_DOCS}/filters/date.html` },
    default:     { description: 'Returns default value if variable is empty/undefined',               since: '1.0',  example: "{{ var|default('fallback') }}",                             link: `${TWIG_DOCS}/filters/default.html` },
    escape:      { description: 'Escapes a string for safe HTML output',                              since: '1.0',  example: '{{ user.username|e }}',                                     link: `${TWIG_DOCS}/filters/escape.html` },
    e:           { description: 'Alias for escape — escapes for safe HTML output',                    since: '1.0',  example: '{{ user.username|e }}',                                     link: `${TWIG_DOCS}/filters/escape.html` },
    first:       { description: 'Returns the first element of a sequence',                            since: '1.0',  example: '{{ items|first }}',                                         link: `${TWIG_DOCS}/filters/first.html` },
    format:      { description: 'Formats a string by replacing placeholders',                         since: '1.0',  example: "{{ 'Hello %s!'|format(name) }}",                            link: `${TWIG_DOCS}/filters/format.html` },
    join:        { description: 'Joins array elements into a string',                                 since: '1.0',  example: "{{ items|join(', ') }}",                                     link: `${TWIG_DOCS}/filters/join.html` },
    json_encode: { description: 'Encodes value as JSON',                                              since: '1.0',  example: '{{ data|json_encode }}',                                     link: `${TWIG_DOCS}/filters/json_encode.html` },
    keys:        { description: 'Returns the keys of a mapping',                                      since: '1.0',  example: '{{ map|keys }}',                                            link: `${TWIG_DOCS}/filters/keys.html` },
    last:        { description: 'Returns the last element of a sequence',                             since: '1.0',  example: '{{ items|last }}',                                          link: `${TWIG_DOCS}/filters/last.html` },
    length:      { description: 'Returns the count of items',                                         since: '1.0',  example: '{{ items|length }}',                                        link: `${TWIG_DOCS}/filters/length.html` },
    lower:       { description: 'Converts a string to lowercase',                                     since: '1.0',  example: "{{ 'HELLO'|lower }}",                                       link: `${TWIG_DOCS}/filters/lower.html` },
    merge:       { description: 'Merges a mapping/sequence with another',                             since: '1.0',  example: '{{ arr|merge([3, 4]) }}',                                   link: `${TWIG_DOCS}/filters/merge.html` },
    nl2br:       { description: 'Inserts HTML line breaks before newlines',                           since: '1.0',  example: '{{ text|nl2br }}',                                          link: `${TWIG_DOCS}/filters/nl2br.html` },
    number_format: { description: 'Formats a number with grouped thousands',                          since: '1.0',  example: '{{ price|number_format(2, ".", ",") }}',                     link: `${TWIG_DOCS}/filters/number_format.html` },
    raw:         { description: 'Marks value as safe (disables auto-escaping) — use with caution',    since: '1.0',  example: '{{ html|raw }}',                                            link: `${TWIG_DOCS}/filters/raw.html` },
    replace:     { description: 'Replaces placeholders in a string',                                  since: '1.0',  example: "{{ 'Hello %name%'|replace({'%name%': 'Fabien'}) }}",        link: `${TWIG_DOCS}/filters/replace.html` },
    reverse:     { description: 'Reverses a sequence or string',                                      since: '1.0',  example: '{{ items|reverse }}',                                       link: `${TWIG_DOCS}/filters/reverse.html` },
    round:       { description: 'Rounds a number',                                                    since: '1.0',  example: '{{ 3.14|round }}',                                          link: `${TWIG_DOCS}/filters/round.html` },
    slice:       { description: 'Extracts a slice of a sequence',                                     since: '1.0',  example: '{{ items|slice(0, 10) }}',                                  link: `${TWIG_DOCS}/filters/slice.html` },
    sort:        { description: 'Sorts a sequence',                                                   since: '1.0',  example: '{{ items|sort }}',                                          link: `${TWIG_DOCS}/filters/sort.html` },
    spaceless:   { description: 'Removes whitespace between HTML tags (DEPRECATED in 3.x)',           since: '1.0',  example: '{{ html|spaceless }}',                                      link: `${TWIG_DOCS}/filters/spaceless.html` },
    split:       { description: 'Splits a string by a delimiter',                                     since: '1.0',  example: "{{ 'a,b,c'|split(',') }}",                                 link: `${TWIG_DOCS}/filters/split.html` },
    striptags:   { description: 'Strips HTML/XML tags from a string',                                 since: '1.0',  example: '{{ html|striptags }}',                                      link: `${TWIG_DOCS}/filters/striptags.html` },
    title:       { description: 'Converts a string to title case',                                    since: '1.0',  example: "{{ 'hello world'|title }}",                                 link: `${TWIG_DOCS}/filters/title.html` },
    trim:        { description: 'Trims whitespace from both ends of a string',                        since: '1.0',  example: "{{ '  hello  '|trim }}",                                   link: `${TWIG_DOCS}/filters/trim.html` },
    upper:       { description: 'Converts a string to uppercase',                                     since: '1.0',  example: "{{ 'hello'|upper }}",                                      link: `${TWIG_DOCS}/filters/upper.html` },
    url_encode:  { description: 'URL-encodes a string',                                               since: '1.0',  example: '{{ url|url_encode }}',                                      link: `${TWIG_DOCS}/filters/url_encode.html` },

    // Functions (excluding names that conflict with tags)
    attribute:   { description: 'Accesses a dynamic attribute/method of a variable',                  since: '1.0',  example: '{{ attribute(obj, method) }}',                              link: `${TWIG_DOCS}/functions/attribute.html` },
    block_func:  { description: 'Renders a block by name (function form)',                            since: '1.0',  example: "{{ block('title') }}",                                      link: `${TWIG_DOCS}/functions/block.html` },
    constant_func: { description: 'Returns the value of a PHP constant',                              since: '1.0',  example: "{{ constant('Post::PUBLISHED') }}",                          link: `${TWIG_DOCS}/functions/constant.html` },
    cycle:       { description: 'Cycles through values',                                              since: '1.0',  example: "{{ cycle(['odd', 'even'], i) }}",                            link: `${TWIG_DOCS}/functions/cycle.html` },
    date_func:   { description: 'Creates a date object (function form)',                              since: '1.0',  example: "{{ date('now') }}",                                         link: `${TWIG_DOCS}/functions/date.html` },
    dump:        { description: 'Dumps variable information for debugging',                           since: '1.0',  example: '{{ dump(user) }}',                                          link: `${TWIG_DOCS}/functions/dump.html` },
    include_func: { description: 'Includes and renders another template',                             since: '1.0',  example: "{{ include('sidebar.html.twig') }}",                         link: `${TWIG_DOCS}/functions/include.html` },
    max:         { description: 'Returns the largest value',                                          since: '1.0',  example: '{{ max(1, 3, 2) }}',                                       link: `${TWIG_DOCS}/functions/max.html` },
    min:         { description: 'Returns the smallest value',                                         since: '1.0',  example: '{{ min(1, 3, 2) }}',                                       link: `${TWIG_DOCS}/functions/min.html` },
    parent:      { description: 'Renders the parent block content',                                   since: '1.0',  example: '{{ parent() }}',                                            link: `${TWIG_DOCS}/functions/parent.html` },
    random:      { description: 'Returns a random value from a sequence',                             since: '1.0',  example: "{{ random(['a', 'b', 'c']) }}",                              link: `${TWIG_DOCS}/functions/random.html` },
    range:       { description: 'Returns a sequence of numbers',                                      since: '1.0',  example: '{% for i in range(0, 3) %}{{ i }}{% endfor %}',             link: `${TWIG_DOCS}/functions/range.html` },
    source:      { description: 'Returns the raw source of a template',                               since: '1.0',  example: "{{ source('template.twig') }}",                             link: `${TWIG_DOCS}/functions/source.html` },
    template_from_string: { description: 'Creates a template from a string',                          since: '1.0',  example: "{{ include(template_from_string('Hello {{ name }}')) }}",    link: `${TWIG_DOCS}/functions/template_from_string.html` },
    path:        { description: '[Symfony] Generates a relative URL path for a route',                since: '—',    example: "{{ path('route_name', {id: 1}) }}",                         link: 'https://symfony.com/doc/current/templates.html#linking-to-pages' },
    url:         { description: '[Symfony] Generates an absolute URL for a route',                    since: '—',    example: "{{ url('route_name', {id: 1}) }}",                          link: 'https://symfony.com/doc/current/templates.html#linking-to-pages' },
    asset:       { description: '[Symfony] Returns the public path of an asset',                      since: '—',    example: "{{ asset('images/logo.png') }}",                            link: 'https://symfony.com/doc/current/templates.html#linking-to-css-javascript-and-image-assets' },
    render:      { description: '[Symfony] Renders a controller fragment inline',                     since: '—',    example: "{{ render(controller('App\\\\Controller\\\\FooController::recent')) }}", link: 'https://symfony.com/doc/current/templates.html#embedding-controllers' },
    csrf_token:  { description: '[Symfony] Generates a CSRF token',                                   since: '—',    example: "{{ csrf_token('authenticate') }}",                          link: 'https://symfony.com/doc/current/security/csrf.html' },
    is_granted:  { description: '[Symfony] Checks if the current user has a given role',              since: '—',    example: "{{ is_granted('ROLE_ADMIN') }}",                            link: 'https://symfony.com/doc/current/security.html' },

    // Tests
    constant:    { description: 'Checks if a variable has the same value as a PHP constant',          since: '1.0',  example: "{% if post.status is constant('Post::PUBLISHED') %}",       link: `${TWIG_DOCS}/tests/constant.html` },
    defined:     { description: 'Checks if a variable is defined',                                    since: '1.0',  example: '{% if users is defined %}',                                 link: `${TWIG_DOCS}/tests/defined.html` },
    divisibleby: { description: 'Checks if a value is divisible by another number',                   since: '1.0',  example: '{% if i is divisibleby(2) %}',                              link: `${TWIG_DOCS}/tests/divisibleby.html` },
    empty:       { description: 'Checks if a sequence or mapping is empty',                           since: '1.0',  example: '{% if posts is empty %}',                                   link: `${TWIG_DOCS}/tests/empty.html` },
    even:        { description: 'Checks if a number is even',                                         since: '1.0',  example: '{% if i is even %}',                                       link: `${TWIG_DOCS}/tests/even.html` },
    iterable:    { description: 'Checks if a variable is iterable',                                   since: '1.0',  example: '{% if var is iterable %}',                                  link: `${TWIG_DOCS}/tests/iterable.html` },
    mapping:     { description: 'Checks if a variable is a mapping (key-value)',                      since: '3.14', example: '{% if x is mapping %}',                                   link: `${TWIG_DOCS}/tests/mapping.html` },
    null:        { description: 'Checks if a variable is null',                                       since: '1.0',  example: '{% if var is null %}',                                      link: `${TWIG_DOCS}/tests/null.html` },
    odd:         { description: 'Checks if a number is odd',                                          since: '1.0',  example: '{% if i is odd %}',                                        link: `${TWIG_DOCS}/tests/odd.html` },
    sameas:      { description: 'Checks if two values are strictly equal (===)',                      since: '1.0',  example: '{% if a is sameas(b) %}',                                   link: `${TWIG_DOCS}/tests/sameas.html` },
    sequence:    { description: 'Checks if a variable is a sequence (list)',                          since: '3.14', example: '{% if x is sequence %}',                                  link: `${TWIG_DOCS}/tests/sequence.html` },

    // Operators
    'not in':    { description: 'Negated containment test — checks if left operand is NOT in right',  since: '1.0',  example: '{% if 1 not in [2, 3] %}',                                  link: `${TWIG_DOCS}/templates.html#containment-operators` },
    'starts with': { description: 'Checks if a string starts with a given prefix',                    since: '1.0',  example: "{% if 'Fabien' starts with 'F' %}",                        link: `${TWIG_DOCS}/templates.html#containment-operators` },
    'ends with': { description: 'Checks if a string ends with a given suffix',                        since: '1.0',  example: "{% if 'Fabien' ends with 'n' %}",                          link: `${TWIG_DOCS}/templates.html#containment-operators` },
    matches:     { description: 'Checks if a string matches a regular expression',                    since: '1.0',  example: "{% if phone matches '/^[\\\\d.]+$/' %}",                    link: `${TWIG_DOCS}/templates.html#containment-operators` },
    'has some':  { description: 'Checks if an iterable has at least one element satisfying a test',   since: '3.x',  example: '{% if sizes has some v => v > 38 %}',                       link: `${TWIG_DOCS}/templates.html#iterable-operators` },
    'has every': { description: 'Checks if every element of an iterable satisfies a test',            since: '3.x',  example: '{% if sizes has every v => v > 38 %}',                      link: `${TWIG_DOCS}/templates.html#iterable-operators` },


    // -- Additional filters --
    column:      { description: 'Returns a column from a nested array/object',                     since: '2.8',  example: '{{ rows|column(0) }}',                                        link: `${TWIG_DOCS}/filters/column.html` },
    country_name: { description: 'Returns the country name for a country code',                     since: '2.12', example: "{{ 'FR'|country_name }}",                                     link: `${TWIG_DOCS}/filters/country_name.html` },
    currency_name: { description: 'Returns the currency name for a currency code',                  since: '2.12', example: "{{ 'EUR'|currency_name }}",                                   link: `${TWIG_DOCS}/filters/currency_name.html` },
    currency_symbol: { description: 'Returns the currency symbol for a currency code',              since: '2.12', example: "{{ 'EUR'|currency_symbol }}",                                 link: `${TWIG_DOCS}/filters/currency_symbol.html` },
    data_uri:    { description: 'Converts a file to a data URI',                                    since: '1.0',  example: '{{ image|data_uri }}',                                         link: `${TWIG_DOCS}/filters/data_uri.html` },
    date_modify: { description: 'Modifies a date with a relative format string',                    since: '1.0',  example: "{{ date|date_modify('+1 day') }}",                              link: `${TWIG_DOCS}/filters/date_modify.html` },
    filter:      { description: 'Applies a filter to each element of a sequence',                   since: '2.9',  example: '{{ items|filter(v => v.active) }}',                             link: `${TWIG_DOCS}/filters/filter.html` },
    find:        { description: 'Finds the first element matching an arrow function',               since: '3.2',  example: '{{ items|find(v => v.active) }}',                               link: `${TWIG_DOCS}/filters/find.html` },
    format_currency: { description: 'Formats a number as currency (Intl-based)',                    since: '2.12', example: "{{ price|format_currency('EUR') }}",                            link: `${TWIG_DOCS}/filters/format_currency.html` },
    format_date: { description: 'Formats a date (Intl-based)',                                      since: '2.12', example: "{{ date|format_date('long') }}",                                link: `${TWIG_DOCS}/filters/format_date.html` },
    format_datetime: { description: 'Formats a datetime (Intl-based)',                              since: '2.12', example: "{{ date|format_datetime('long', 'short') }}",                  link: `${TWIG_DOCS}/filters/format_datetime.html` },
    format_number: { description: 'Formats a number (Intl-based)',                                  since: '2.12', example: '{{ price|format_number }}',                                     link: `${TWIG_DOCS}/filters/format_number.html` },
    format_time: { description: 'Formats a time (Intl-based)',                                      since: '2.12', example: "{{ time|format_time('short') }}",                               link: `${TWIG_DOCS}/filters/format_time.html` },
    html_attr_merge: { description: 'Merges HTML attribute-value pairs',                            since: '3.18', example: '{{ attrs|html_attr_merge }}',                                   link: `${TWIG_DOCS}/filters/html_attr_merge.html` },
    html_attr_type: { description: 'Detects the type of an HTML attribute value',                   since: '3.18', example: "{{ 'text'|html_attr_type }}",                                   link: `${TWIG_DOCS}/filters/html_attr_type.html` },
    html_to_markdown: { description: 'Converts HTML to Markdown',                                   since: '2.12', example: '{{ html|html_to_markdown }}',                                    link: `${TWIG_DOCS}/filters/html_to_markdown.html` },
    inky_to_html: { description: 'Converts Inky (Foundation for Emails) to HTML',                   since: '2.12', example: '{{ email|inky_to_html }}',                                      link: `${TWIG_DOCS}/filters/inky_to_html.html` },
    inline_css:  { description: 'Inlines CSS styles into HTML elements',                            since: '3.10', example: '{{ html|inline_css }}',                                          link: `${TWIG_DOCS}/filters/inline_css.html` },
    invoke:      { description: 'Calls an arrow function with arguments',                           since: '3.19', example: '{{ fn|invoke(arg1, arg2) }}',                                   link: `${TWIG_DOCS}/filters/invoke.html` },
    language_name: { description: 'Returns the language name for a locale code',                    since: '2.12', example: "{{ 'fr'|language_name }}",                                      link: `${TWIG_DOCS}/filters/language_name.html` },
    locale_name: { description: 'Returns the locale name for a locale code',                        since: '2.12', example: "{{ 'fr_FR'|locale_name }}",                                     link: `${TWIG_DOCS}/filters/locale_name.html` },
    map:         { description: 'Applies an arrow function to each element of a sequence',          since: '2.9',  example: '{{ people|map(p => p.first_name)|join(", ") }}',               link: `${TWIG_DOCS}/filters/map.html` },
    markdown_to_html: { description: 'Converts Markdown to HTML',                                   since: '2.12', example: '{{ text|markdown_to_html }}',                                    link: `${TWIG_DOCS}/filters/markdown_to_html.html` },
    plural:      { description: 'Converts a noun to its plural form',                               since: '3.16', example: "{{ 'person'|plural }}",                                         link: `${TWIG_DOCS}/filters/plural.html` },
    reduce:      { description: 'Reduces a sequence to a single value via an arrow function',       since: '2.9',  example: '{{ items|reduce((carry, v) => carry + v) }}',                    link: `${TWIG_DOCS}/filters/reduce.html` },
    shuffle:     { description: 'Randomly shuffles the elements of a sequence',                     since: '3.16', example: '{{ items|shuffle }}',                                           link: `${TWIG_DOCS}/filters/shuffle.html` },
    singular:    { description: 'Converts a noun to its singular form',                             since: '3.16', example: "{{ 'people'|singular }}",                                       link: `${TWIG_DOCS}/filters/singular.html` },
    slug:        { description: 'Converts a string to a URL-safe slug',                             since: '1.0',  example: "{{ 'Hello World'|slug }}",                                      link: `${TWIG_DOCS}/filters/slug.html` },
    timezone_name: { description: 'Returns the timezone name for a timezone code',                  since: '2.12', example: "{{ 'Europe/Paris'|timezone_name }}",                            link: `${TWIG_DOCS}/filters/timezone_name.html` },
    u:           { description: 'Shortcut for Unicode-aware string conversion',                     since: '2.12', example: "{{ 'Hello'|u }}",                                              link: `${TWIG_DOCS}/filters/u.html` },

    // -- Additional functions --
    country_names: { description: 'Returns all country names keyed by country code',                since: '3.12', example: '{{ country_names() }}',                                         link: `${TWIG_DOCS}/functions/country_names.html` },
    country_timezones: { description: 'Returns all timezones for a given country code',             since: '3.12', example: "{{ country_timezones('FR') }}",                                 link: `${TWIG_DOCS}/functions/country_timezones.html` },
    currency_names: { description: 'Returns all currency names keyed by currency code',             since: '3.12', example: '{{ currency_names() }}',                                        link: `${TWIG_DOCS}/functions/currency_names.html` },
    enum:        { description: 'Creates an enum instance from a fully qualified class name',        since: '3.15', example: "{{ enum('App\\Enum\\Status') }}",                            link: `${TWIG_DOCS}/functions/enum.html` },
    enum_cases:  { description: 'Returns all cases of an enum',                                     since: '3.17', example: "{{ enum_cases('App\\Enum\\Status') }}",                      link: `${TWIG_DOCS}/functions/enum_cases.html` },
    html_attr:   { description: 'Generates HTML attribute-value pairs from a mapping',              since: '3.18', example: "{{ html_attr({class: 'btn', id: 'submit'}) }}",                  link: `${TWIG_DOCS}/functions/html_attr.html` },
    html_classes: { description: 'Generates CSS class strings with conditional logic',              since: '3.17', example: "{{ html_classes('btn', {primary: isPrimary}) }}",                link: `${TWIG_DOCS}/functions/html_classes.html` },
    html_cva:    { description: 'Class Variance Authority — generates class strings with variants', since: '3.17', example: "{{ html_cva({base: 'btn', variants: {size: {sm: 'btn-sm'}}}) }}", link: `${TWIG_DOCS}/functions/html_cva.html` },
    language_names: { description: 'Returns all language names keyed by language code',             since: '3.12', example: '{{ language_names() }}',                                        link: `${TWIG_DOCS}/functions/language_names.html` },
    locale_names: { description: 'Returns all locale names keyed by locale code',                   since: '3.12', example: '{{ locale_names() }}',                                          link: `${TWIG_DOCS}/functions/locale_names.html` },
    script_names: { description: 'Returns all script names keyed by script code',                   since: '3.12', example: '{{ script_names() }}',                                          link: `${TWIG_DOCS}/functions/script_names.html` },
    timezone_names: { description: 'Returns all timezone names keyed by timezone code',             since: '3.12', example: '{{ timezone_names() }}',                                        link: `${TWIG_DOCS}/functions/timezone_names.html` },

    // -- Additional tests --
    'divisible by': { description: 'Checks if a value is divisible by a number (multi-word)',       since: '1.0',  example: '{% if i is divisible by 2 %}',                                  link: `${TWIG_DOCS}/tests/divisibleby.html` },
    'same as':    { description: 'Checks if two values are strictly equal (===) (multi-word)',      since: '1.0',  example: '{% if a is same as(b) %}',                                      link: `${TWIG_DOCS}/tests/sameas.html` },



    // -- Symfony Tags --
    form_theme:  { description: '[Symfony] Sets form theme resources for a form view',               since: '—',    example: '{% form_theme form "form/fields.html.twig" %}',              link: 'https://symfony.com/doc/current/form/form_customization.html' },
    trans:       { description: '[Symfony] Renders translated content block',                        since: '—',    example: '{% trans %}Hello %name%{% endtrans %}',                      link: 'https://symfony.com/doc/current/translation.html' },
    trans_default_domain: { description: '[Symfony] Sets the default translation domain for a template', since: '—', example: '{% trans_default_domain "app" %}',                             link: 'https://symfony.com/doc/current/translation.html' },
    stopwatch:   { description: '[Symfony] Times a template block in the profiler',                  since: '—',    example: "{% stopwatch 'event_name' %}...{% endstopwatch %}",            link: 'https://symfony.com/doc/current/performance.html' },

    // -- Symfony Filters --
    humanize:    { description: '[Symfony] Transforms a string to human-readable form',              since: '—',    example: "{{ 'date_of_birth'|humanize }}",                               link: 'https://symfony.com/doc/current/reference/twig_reference.html' },
    trans_filter: { description: '[Symfony] Translates text (filter form)',                           since: '—',    example: "{{ 'message'|trans }}",                                       link: 'https://symfony.com/doc/current/translation.html' },
    sanitize_html: { description: '[Symfony] Sanitizes HTML content',                                since: '—',    example: '{{ body|sanitize_html }}',                                    link: 'https://symfony.com/doc/current/html_sanitizer.html' },
    yaml_encode: { description: '[Symfony] Encodes value as YAML',                                   since: '—',    example: '{{ data|yaml_encode }}',                                      link: 'https://symfony.com/doc/current/reference/twig_reference.html' },
    yaml_dump:   { description: '[Symfony] Dumps value as YAML with type info',                      since: '—',    example: '{{ data|yaml_dump }}',                                        link: 'https://symfony.com/doc/current/reference/twig_reference.html' },
    abbr_class:  { description: '[Symfony] Generates <abbr> for a PHP class name',                   since: '—',    example: "{{ 'App\\Entity\\Product'|abbr_class }}",                  link: 'https://symfony.com/doc/current/reference/twig_reference.html' },
    abbr_method: { description: '[Symfony] Generates <abbr> for a PHP method name',                  since: '—',    example: "{{ 'App\\Controller\\ProductController::list'|abbr_method }}", link: 'https://symfony.com/doc/current/reference/twig_reference.html' },
    serialize:   { description: '[Symfony] Serializes data to a string (JSON, XML, etc.)',           since: '—',    example: "{{ object|serialize('json') }}",                               link: 'https://symfony.com/doc/current/reference/twig_reference.html' },
    emojify:     { description: '[Symfony] Converts emoji codes to actual emoji',                    since: '—',    example: "{{ ':+1:'|emojify }}",                                         link: 'https://symfony.com/doc/current/reference/twig_reference.html' },
    file_excerpt: { description: '[Symfony] Shows a code excerpt around a given line',               since: '—',    example: "{{ '/path/to/file'|file_excerpt(line=10) }}",                  link: 'https://symfony.com/doc/current/reference/twig_reference.html' },
    format_file: { description: '[Symfony] Generates a file path link',                              since: '—',    example: "{{ file|format_file(line=1, text='Open') }}",                  link: 'https://symfony.com/doc/current/reference/twig_reference.html' },
    file_link:   { description: '[Symfony] Generates a link to a file at a line',                    since: '—',    example: "{{ 'file.txt'|file_link(line=3) }}",                           link: 'https://symfony.com/doc/current/reference/twig_reference.html' },
    file_relative: { description: '[Symfony] Converts absolute path to project-relative',            since: '—',    example: "{{ '/var/www/app/templates/index.html.twig'|file_relative }}", link: 'https://symfony.com/doc/current/reference/twig_reference.html' },

    // -- Symfony Functions (extended) --
    render_esi:  { description: '[Symfony] Renders with ESI caching strategy',                       since: '—',    example: "{{ render_esi(controller('App\\Controller\\FooController::recent')) }}", link: 'https://symfony.com/doc/current/reference/twig_reference.html' },
    fragment_uri: { description: '[Symfony] Generates a fragment URI',                               since: '—',    example: '{{ fragment_uri(controller(...)) }}',                         link: 'https://symfony.com/doc/current/reference/twig_reference.html' },
    controller:   { description: '[Symfony] Returns a ControllerReference for render()',             since: '—',    example: "{{ render(controller('App\\Controller\\BlogController::latest', {max: 3})) }}", link: 'https://symfony.com/doc/current/reference/twig_reference.html' },
    asset_version: { description: '[Symfony] Returns the current version of an asset package',       since: '—',    example: "{{ asset_version('avatar.png', 'foo_package') }}",           link: 'https://symfony.com/doc/current/reference/twig_reference.html' },
    absolute_url: { description: '[Symfony] Converts a relative path to absolute URL',               since: '—',    example: "{{ absolute_url(path('route')) }}",                           link: 'https://symfony.com/doc/current/reference/twig_reference.html' },
    relative_path: { description: '[Symfony] Converts absolute URL to relative path',                since: '—',    example: "{{ relative_path('http://example.com/human.txt') }}",         link: 'https://symfony.com/doc/current/reference/twig_reference.html' },
    expression:  { description: '[Symfony] Creates an Expression object',                            since: '—',    example: '{{ expression(1 + 2) }}',                                     link: 'https://symfony.com/doc/current/reference/twig_reference.html' },
    impersonation_path: { description: '[Symfony] Generates URL to impersonate a user',              since: '—',    example: "{{ impersonation_path('user@example.com') }}",                link: 'https://symfony.com/doc/current/reference/twig_reference.html' },
    impersonation_url: { description: '[Symfony] Generates absolute URL to impersonate a user',      since: '—',    example: "{{ impersonation_url('user@example.com') }}",                 link: 'https://symfony.com/doc/current/reference/twig_reference.html' },
    impersonation_exit_path: { description: '[Symfony] Generates URL to exit impersonation',         since: '—',    example: "{{ impersonation_exit_path('/dashboard') }}",                 link: 'https://symfony.com/doc/current/reference/twig_reference.html' },
    impersonation_exit_url: { description: '[Symfony] Generates absolute URL to exit impersonation', since: '—',    example: "{{ impersonation_exit_url('/dashboard') }}",                  link: 'https://symfony.com/doc/current/reference/twig_reference.html' },
    logout_path: { description: '[Symfony] Generates relative logout URL',                           since: '—',    example: "{{ logout_path('main') }}",                                   link: 'https://symfony.com/doc/current/reference/twig_reference.html' },
    logout_url:  { description: '[Symfony] Generates absolute logout URL',                           since: '—',    example: "{{ logout_url('main') }}",                                    link: 'https://symfony.com/doc/current/reference/twig_reference.html' },
    is_granted_for_user: { description: '[Symfony] Checks authorization for a specific user',        since: '—',    example: "{{ is_granted_for_user(user, 'ROLE_ADMIN') }}",              link: 'https://symfony.com/doc/current/reference/twig_reference.html' },
    t:           { description: '[Symfony] Creates a Translatable object for translation',           since: '—',    example: "{{ t('message', {'%name%': 'John'}, 'blog')|trans }}",       link: 'https://symfony.com/doc/current/reference/twig_reference.html' },
    importmap:   { description: '[Symfony] Outputs the importmap (AssetMapper)',                     since: '—',    example: '{{ importmap() }}',                                           link: 'https://symfony.com/doc/current/frontend/asset_mapper.html' },

    // -- Symfony Form Functions --
    form:        { description: '[Symfony] Renders an entire form',                                  since: '—',    example: '{{ form(form) }}',                                            link: 'https://symfony.com/doc/current/form/form_customization.html' },
    form_start:  { description: '[Symfony] Renders the start tag of a form',                         since: '—',    example: '{{ form_start(form) }}',                                      link: 'https://symfony.com/doc/current/form/form_customization.html' },
    form_end:    { description: '[Symfony] Renders the end tag of a form',                           since: '—',    example: '{{ form_end(form) }}',                                        link: 'https://symfony.com/doc/current/form/form_customization.html' },
    form_widget: { description: '[Symfony] Renders the HTML widget of a field',                      since: '—',    example: "{{ form_widget(form.name, {'attr': {'class': 'foo'}}) }}",    link: 'https://symfony.com/doc/current/form/form_customization.html' },
    form_label:  { description: '[Symfony] Renders the label for a field',                           since: '—',    example: "{{ form_label(form.name, 'Your Name') }}",                    link: 'https://symfony.com/doc/current/form/form_customization.html' },
    form_help:   { description: '[Symfony] Renders the help text for a field',                       since: '—',    example: '{{ form_help(form.name) }}',                                  link: 'https://symfony.com/doc/current/form/form_customization.html' },
    form_errors: { description: '[Symfony] Renders validation errors for a field',                   since: '—',    example: '{{ form_errors(form.name) }}',                                link: 'https://symfony.com/doc/current/form/form_customization.html' },
    form_row:    { description: '[Symfony] Renders the complete row of a field',                     since: '—',    example: "{{ form_row(form.name, {'label': 'foo'}) }}",                 link: 'https://symfony.com/doc/current/form/form_customization.html' },
    form_rest:   { description: '[Symfony] Renders all unrendered fields',                           since: '—',    example: '{{ form_rest(form) }}',                                       link: 'https://symfony.com/doc/current/form/form_customization.html' },
    form_parent: { description: '[Symfony] Returns the parent form view',                            since: '—',    example: '{{ form_parent(form) }}',                                     link: 'https://symfony.com/doc/current/form/form_customization.html' },
    field_name:  { description: '[Symfony] Returns the name attribute of a form field',              since: '—',    example: '{{ field_name(form.username) }}',                             link: 'https://symfony.com/doc/current/form/form_customization.html' },
    field_value: { description: '[Symfony] Returns the current value of a form field',               since: '—',    example: '{{ field_value(form.username) }}',                            link: 'https://symfony.com/doc/current/form/form_customization.html' },
    field_label: { description: '[Symfony] Returns the label text of a form field',                  since: '—',    example: '{{ field_label(form.username) }}',                            link: 'https://symfony.com/doc/current/form/form_customization.html' },
    field_help:  { description: '[Symfony] Returns the help text of a form field',                   since: '—',    example: '{{ field_help(form.username) }}',                             link: 'https://symfony.com/doc/current/form/form_customization.html' },
    field_errors: { description: '[Symfony] Returns errors for a form field',                        since: '—',    example: '{{ field_errors(form.username) }}',                           link: 'https://symfony.com/doc/current/form/form_customization.html' },
    field_id:    { description: '[Symfony] Returns the id attribute of a form field',                since: '—',    example: '{{ field_id(form.username) }}',                               link: 'https://symfony.com/doc/current/form/form_customization.html' },
    field_choices: { description: '[Symfony] Returns choices iterator for a choice field',           since: '—',    example: '{% for label, value in field_choices(form.country) %}',       link: 'https://symfony.com/doc/current/form/form_customization.html' },

    // -- Symfony Tests --
    selectedchoice: { description: '[Symfony] Checks if a choice is selected',                       since: '—',    example: '{% if choice is selectedchoice(value) %}selected{% endif %}', link: 'https://symfony.com/doc/current/form/form_customization.html' },
    rootform:    { description: '[Symfony] Checks if a form is the root form',                       since: '—',    example: '{% if form is rootform %}',                                   link: 'https://symfony.com/doc/current/form/form_customization.html' },


};

export const END_TAG_MAP: Record<string, string> = {
    apply: 'endapply', autoescape: 'endautoescape', block: 'endblock',
    cache: 'endcache', deprecated: 'enddeprecated', embed: 'endembed',
    for: 'endfor', guard: 'endguard', if: 'endif', macro: 'endmacro',
    sandbox: 'endsandbox', set: 'endset', types: 'endtypes',
    verbatim: 'endverbatim', with: 'endwith',
};

// Add end tag entries
for (const [start, end] of Object.entries(END_TAG_MAP)) {
    BUILTIN_HOVER_DATA[end] = {
        description: `Closes a \`{% ${start} %}\` block`,
        since: '—',
        example: `{% ${end} %}`,
        link: BUILTIN_HOVER_DATA[start]?.link ?? `${TWIG_DOCS}/tags/${start}.html`,
    };
}

export class TwigHoverProvider implements vscode.HoverProvider {
    provideHover(
        document: vscode.TextDocument,
        position: vscode.Position,
    ): vscode.ProviderResult<vscode.Hover> {
        const range = document.getWordRangeAtPosition(position, /[\w.]+/);
        if (range === undefined) return null;

        const word = document.getText(range);

        // Check for filter: word after |
        const linePrefix = document.lineAt(position).text.substring(0, position.character);
        const filterMatch = linePrefix.match(/\|\s*([\w.]+)$/);
        const lookup = filterMatch !== null ? filterMatch[1] : word;

        const entry = BUILTIN_HOVER_DATA[lookup];
        if (entry === undefined) return null;

        const content = new vscode.MarkdownString(
            `### \`${lookup}\`\n\n${entry.description}\n\n` +
            `> Since Twig ${entry.since}  \n` +
            `> Example: \`${entry.example}\`  \n\n` +
            `[Twig Docs](${entry.link})`,
        );
        content.isTrusted = true;

        return new vscode.Hover(content, range);
    }
}

// ═══════════════════════════════════════════════════════════════════════
// 11. Definition provider — go-to template for extends/include/embed
// ═══════════════════════════════════════════════════════════════════════

export const TEMPLATE_PATH_TAGS = new Set(['extends', 'include', 'embed', 'import', 'from', 'use']);

// Tags/functions that reference template paths
const TEMPLATE_PATH_FUNCTIONS = new Set(['include', 'source', 'block']);

export class TwigDefinitionProvider implements vscode.DefinitionProvider {
    provideDefinition(
        document: vscode.TextDocument,
        position: vscode.Position,
    ): vscode.ProviderResult<vscode.Definition | vscode.LocationLink[]> {
        const line = document.lineAt(position).text;
        const beforeCursor = line.substring(0, position.character);
        const afterCursor = line.substring(position.character);

        // 1. {% tag 'path' %} — template path in tag
        const tagMatch = beforeCursor.match(/\{%\s*(\w+)\s*(['"])([^'"]*)$/);
        if (tagMatch !== null && TEMPLATE_PATH_TAGS.has(tagMatch[1])) {
            return this.resolveTemplatePath(document, beforeCursor, afterCursor, tagMatch[3]);
        }

        // 2. {{ include('path') }} — template path in function call
        const funcMatch = beforeCursor.match(/\b(include|source)\s*\(\s*(['"])([^'"]*)$/);
        if (funcMatch !== null) {
            return this.resolveTemplatePath(document, beforeCursor, afterCursor, funcMatch[3]);
        }

        // 3. {{ path('route_name') }} — route name (navigate to route definition if found)
        const routeMatch = beforeCursor.match(/\b(?:path|url)\s*\(\s*(['"])([^'"]*)$/);
        if (routeMatch !== null) {
            return this.resolveRouteName(document, beforeCursor, afterCursor, routeMatch[2]);
        }

        // 4. {{ asset('path') }} — asset path
        const assetMatch = beforeCursor.match(/\basset\s*\(\s*(['"])([^'"]*)$/);
        if (assetMatch !== null) {
            return this.resolveAssetPath(document, beforeCursor, afterCursor, assetMatch[2]);
        }

        return null;
    }

    private resolveTemplatePath(
        document: vscode.TextDocument,
        before: string, after: string, partial: string,
    ): vscode.ProviderResult<vscode.Definition | vscode.LocationLink[]> {
        const restMatch = after.match(/^([^'"]*)(['"])/);
        const fullPath = restMatch !== null ? partial + restMatch[1] : partial;

        const clean = fullPath.replace(/^['"]|['"]$/g, '');
        const baseDir = path.dirname(document.uri.fsPath);
        const workspaceDir = vscode.workspace.workspaceFolders?.[0]?.uri.fsPath ?? baseDir;

        // Strategy 1: @Bundle notation → convert to paths
        if (clean.startsWith('@')) {
            const atPath = clean.replace(/^@(\w+)\//, 'bundles/$1/');
            const twigDir = path.join(workspaceDir, 'templates', atPath);
            if (fs.existsSync(twigDir)) return new vscode.Location(vscode.Uri.file(twigDir), new vscode.Position(0, 0));
            const srcDir = path.join(workspaceDir, 'src', atPath, 'Resources', 'views');
            if (fs.existsSync(srcDir)) return new vscode.Location(vscode.Uri.file(srcDir), new vscode.Position(0, 0));
        }

        // Strategy 2: Relative to current file
        const relative = path.join(baseDir, clean);
        if (fs.existsSync(relative)) return new vscode.Location(vscode.Uri.file(relative), new vscode.Position(0, 0));

        // Strategy 3: With .twig extensions
        if (!clean.endsWith('.twig') && !clean.endsWith('.html.twig')) {
            for (const ext of ['.twig', '.html.twig']) {
                const p = path.join(baseDir, clean + ext);
                if (fs.existsSync(p)) return new vscode.Location(vscode.Uri.file(p), new vscode.Position(0, 0));
            }
        }

        // Strategy 4: templates/ directory (Symfony convention)
        for (const templatesDir of ['templates', 'Resources/views']) {
            const p = path.join(workspaceDir, templatesDir, clean);
            if (fs.existsSync(p)) return new vscode.Location(vscode.Uri.file(p), new vscode.Position(0, 0));
            if (!clean.endsWith('.twig')) {
                for (const ext of ['.twig', '.html.twig']) {
                    const pe = path.join(workspaceDir, templatesDir, clean + ext);
                    if (fs.existsSync(pe)) return new vscode.Location(vscode.Uri.file(pe), new vscode.Position(0, 0));
                }
            }
        }

        // Strategy 5: Namespaced paths (e.g., 'admin/template' → templates/admin/template.html.twig)
        if (clean.includes('/')) {
            for (const templatesDir of ['templates', 'Resources/views']) {
                const p = path.join(workspaceDir, templatesDir, clean);
                if (fs.existsSync(p)) return new vscode.Location(vscode.Uri.file(p), new vscode.Position(0, 0));
                for (const ext of ['.twig', '.html.twig']) {
                    const pe = path.join(workspaceDir, templatesDir, clean + ext);
                    if (fs.existsSync(pe)) return new vscode.Location(vscode.Uri.file(pe), new vscode.Position(0, 0));
                }
            }
        }

        return null;
    }

    private resolveRouteName(
        document: vscode.TextDocument,
        before: string, after: string, partial: string,
    ): vscode.ProviderResult<vscode.Definition | vscode.LocationLink[]> {
        // Find route definitions in YAML/PHP/Attribute files
        const restMatch = after.match(/^([^'"]*)(['"])/);
        const routeName = restMatch !== null ? partial + restMatch[1] : partial;
        const workspaceDir = vscode.workspace.workspaceFolders?.[0]?.uri.fsPath;

        if (workspaceDir === undefined) return null;

        // Search for route definition in common locations
        const searchPaths = [
            path.join(workspaceDir, 'config', 'routes'),
            path.join(workspaceDir, 'config'),
            path.join(workspaceDir, 'src'),
        ];

        for (const searchPath of searchPaths) {
            if (!fs.existsSync(searchPath)) continue;
            try {
                const files = this.findRouteDefinition(searchPath, routeName);
                if (files.length > 0) {
                    return new vscode.Location(vscode.Uri.file(files[0]), new vscode.Position(0, 0));
                }
            } catch { /* ignore */ }
        }

        return null;
    }

    private findRouteDefinition(dir: string, routeName: string): string[] {
        const results: string[] = [];
        try {
            const entries = fs.readdirSync(dir, { withFileTypes: true });
            for (const entry of entries) {
                const fullPath = path.join(dir, entry.name);
                if (entry.isDirectory()) {
                    results.push(...this.findRouteDefinition(fullPath, routeName));
                } else if (entry.isFile() && /\.(yaml|yml|php|xml)$/.test(entry.name)) {
                    const content = fs.readFileSync(fullPath, 'utf-8');
                    // YAML: name: or path: pattern
                    // PHP: #[Route('/path', name: 'route_name')]
                    // XML: <route id="route_name"
                    if (content.includes(`'${routeName}'`) ||
                        content.includes(`"${routeName}"`) ||
                        content.includes(`name: ${routeName}`) ||
                        content.includes(`id="${routeName}"`)) {
                        results.push(fullPath);
                    }
                }
            }
        } catch { /* ignore */ }
        return results;
    }

    private resolveAssetPath(
        document: vscode.TextDocument,
        before: string, after: string, partial: string,
    ): vscode.ProviderResult<vscode.Definition | vscode.LocationLink[]> {
        const restMatch = after.match(/^([^'"]*)(['"])/);
        const assetPath = restMatch !== null ? partial + restMatch[1] : partial;
        const workspaceDir = vscode.workspace.workspaceFolders?.[0]?.uri.fsPath;

        if (workspaceDir === undefined) return null;

        // Look in public/ directory (Symfony convention)
        const publicPath = path.join(workspaceDir, 'public', assetPath);
        if (fs.existsSync(publicPath)) {
            return new vscode.Location(vscode.Uri.file(publicPath), new vscode.Position(0, 0));
        }

        // Also try assets/ directory
        const assetsPath = path.join(workspaceDir, 'assets', assetPath);
        if (fs.existsSync(assetsPath)) {
            return new vscode.Location(vscode.Uri.file(assetsPath), new vscode.Position(0, 0));
        }

        return null;
    }
}

// ═══════════════════════════════════════════════════════════════════════
// 12. Completion provider — Twig keywords
// ═══════════════════════════════════════════════════════════════════════

export const TWIG_COMPLETIONS: readonly vscode.CompletionItem[] = [
    ...['apply','autoescape','block','cache','deprecated','embed','for','guard','if','macro','sandbox','set','verbatim','with'].map(tag => {
        const item = new vscode.CompletionItem(tag, vscode.CompletionItemKind.Keyword);
        item.detail = 'Twig Block Tag';
        item.insertText = new vscode.SnippetString(`${tag} $1 %}\n$0\n{% end${tag} %}`);
        return item;
    }),
    ...['do','extends','flush','from','import','include','use'].map(tag => {
        const item = new vscode.CompletionItem(tag, vscode.CompletionItemKind.Keyword);
        item.detail = 'Twig Tag';
        item.insertText = new vscode.SnippetString(`${tag} $1 %}`);
        return item;
    }),
    ...['e','upper','lower','title','trim','date','default','escape','first','last','length','keys','join','json_encode','raw','replace','reverse','round','slice','sort','split','striptags','url_encode','abs','batch','capitalize','merge','nl2br','number_format','format'].map(f => {
        const item = new vscode.CompletionItem(f, vscode.CompletionItemKind.Function);
        item.detail = 'Twig Filter';
        item.insertText = new vscode.SnippetString(f);
        return item;
    }),
    ...['range','cycle','date','dump','include','max','min','parent','random','source','attribute','block','constant','path','url','asset','render','csrf_token','is_granted'].map(fn => {
        const item = new vscode.CompletionItem(fn, vscode.CompletionItemKind.Function);
        item.detail = 'Twig Function';
        item.insertText = new vscode.SnippetString(`${fn}($1)`);
        return item;
    }),
];

export class TwigCompletionProvider implements vscode.CompletionItemProvider {
    provideCompletionItems(document: vscode.TextDocument, position: vscode.Position): vscode.ProviderResult<vscode.CompletionItem[]> {
        const linePrefix = document.lineAt(position).text.substring(0, position.character);
        if (linePrefix.match(/\{%\s*\w*$/)) return TWIG_COMPLETIONS.filter(c => c.kind === vscode.CompletionItemKind.Keyword);
        if (linePrefix.match(/\|\s*\w*$/)) return TWIG_COMPLETIONS.filter(c => c.detail === 'Twig Filter');
        if (linePrefix.includes('{{') && !linePrefix.includes('}}')) return TWIG_COMPLETIONS.filter(c => c.detail === 'Twig Function' || c.detail === 'Twig Filter');
        return [];
    }
}

// ═══════════════════════════════════════════════════════════════════════
// 13. Symbol + Folding providers
// ═══════════════════════════════════════════════════════════════════════

export class TwigSymbolProvider implements vscode.DocumentSymbolProvider {
    provideDocumentSymbols(document: vscode.TextDocument): vscode.ProviderResult<vscode.SymbolInformation[] | vscode.DocumentSymbol[]> {
        const symbols: vscode.DocumentSymbol[] = [];
        for (let i = 0; i < document.lineCount; i++) {
            const line = document.lineAt(i).text;
            const blockMatch = line.match(/\{%-?\s*block\s+(\w+)/);
            const macroMatch = line.match(/\{%-?\s*macro\s+(\w+)/);
            if (blockMatch) {
                const range = new vscode.Range(i, 0, i, line.length);
                symbols.push(new vscode.DocumentSymbol(blockMatch[1], 'Block', vscode.SymbolKind.Module, range, range));
            } else if (macroMatch) {
                const range = new vscode.Range(i, 0, i, line.length);
                symbols.push(new vscode.DocumentSymbol(macroMatch[1], 'Macro', vscode.SymbolKind.Function, range, range));
            }
        }
        return symbols;
    }
}

export class TwigFoldingProvider implements vscode.FoldingRangeProvider {
    provideFoldingRanges(document: vscode.TextDocument): vscode.ProviderResult<vscode.FoldingRange[]> {
        const folds: vscode.FoldingRange[] = [];
        const stack: { start: number; tag: string }[] = [];
        const startRe = /\{%-?\s*(block|for|if|macro|apply|autoescape|embed|cache|deprecated|guard|sandbox|set|verbatim|with)\b/;
        const endRe = /\{%-?\s*(endblock|endfor|endif|endmacro|endapply|endautoescape|endembed|endcache|enddeprecated|endguard|endsandbox|endset|endverbatim|endwith)\b/;
        for (let i = 0; i < document.lineCount; i++) {
            const line = document.lineAt(i).text;
            const sm = line.match(startRe);
            if (sm && !(sm[1] === 'set' && line.includes('endset'))) stack.push({ start: i, tag: sm[1] });
            const em = line.match(endRe);
            if (em && stack.length > 0) {
                const o = stack.pop()!;
                if (o.start < i) folds.push(new vscode.FoldingRange(o.start, i, vscode.FoldingRangeKind.Region));
            }
        }
        return folds;
    }
}

// ═══════════════════════════════════════════════════════════════════════
// 14. Signature help
// ═══════════════════════════════════════════════════════════════════════

const TWIG_SIGNATURES: Record<string, { label: string; params: vscode.ParameterInformation[] }> = {
    range:      { label: 'range(low, high, step?)',          params: [new vscode.ParameterInformation('low', 'Start'), new vscode.ParameterInformation('high', 'End'), new vscode.ParameterInformation('step', 'Increment')] },
    path:       { label: 'path(route, params?)',              params: [new vscode.ParameterInformation('route', 'Route name'), new vscode.ParameterInformation('params', 'Parameters')] },
    url:        { label: 'url(route, params?)',               params: [new vscode.ParameterInformation('route', 'Route name'), new vscode.ParameterInformation('params', 'Parameters')] },
    dump:       { label: 'dump(...variables)',                params: [new vscode.ParameterInformation('variables', 'Variables to dump')] },
    include:    { label: 'include(template, vars?)',          params: [new vscode.ParameterInformation('template', 'Template path'), new vscode.ParameterInformation('vars', 'Variables')] },
    block:      { label: 'block(name)',                       params: [new vscode.ParameterInformation('name', 'Block name')] },
    constant:   { label: 'constant(name)',                    params: [new vscode.ParameterInformation('name', 'PHP constant')] },
    is_granted: { label: 'is_granted(role, object?)',         params: [new vscode.ParameterInformation('role', 'Role'), new vscode.ParameterInformation('object', 'Subject')] },
    render:     { label: 'render(controller, options?)',      params: [new vscode.ParameterInformation('controller', 'Controller'), new vscode.ParameterInformation('options', 'Options')] },
    csrf_token: { label: 'csrf_token(intention)',             params: [new vscode.ParameterInformation('intention', 'Intention')] },
    max:        { label: 'max(...values)',                    params: [new vscode.ParameterInformation('values', 'Values')] },
    min:        { label: 'min(...values)',                    params: [new vscode.ParameterInformation('values', 'Values')] },
};

export class TwigSignatureHelpProvider implements vscode.SignatureHelpProvider {
    provideSignatureHelp(document: vscode.TextDocument, position: vscode.Position): vscode.ProviderResult<vscode.SignatureHelp> {
        const lp = document.lineAt(position).text.substring(0, position.character);
        const m = lp.match(/(\w+)\s*\($/);
        if (!m) return null;
        const s = TWIG_SIGNATURES[m[1]];
        if (!s) return null;
        const h = new vscode.SignatureHelp();
        h.signatures = [new vscode.SignatureInformation(s.label, new vscode.MarkdownString(`**${m[1]}** — Twig function`))];
        h.signatures[0].parameters = s.params;
        h.activeSignature = 0;
        h.activeParameter = Math.min((lp.substring(m[0].length).match(/,/g) ?? []).length, s.params.length - 1);
        return h;
    }
}

// ═══════════════════════════════════════════════════════════════════════
// 15. Code Actions (Quick Fix)
// ═══════════════════════════════════════════════════════════════════════

export class TwigCodeActionProvider implements vscode.CodeActionProvider {
    provideCodeActions(
        document: vscode.TextDocument,
        range: vscode.Range | vscode.Selection,
        context: vscode.CodeActionContext,
    ): vscode.ProviderResult<(vscode.CodeAction | vscode.Command)[]> {
        const actions: vscode.CodeAction[] = [];

        for (const diag of context.diagnostics) {
            if (diag.source !== 'twig-analyzer') continue;

            const code = typeof diag.code === 'string' ? diag.code : '';

            // Quick fix: add |e escape filter
            if (code === 'TWIG-RAW-FILTER' || code === 'TWIG-MISSING-ESCAPE') {
                const fix = new vscode.CodeAction('Add |e escape filter', vscode.CodeActionKind.QuickFix);
                fix.diagnostics = [diag];
                fix.edit = new vscode.WorkspaceEdit();
                const line = document.lineAt(diag.range.end.line);
                const afterEnd = line.text.substring(diag.range.end.character);
                // Find }} to insert before
                const endPos = line.text.indexOf('}}', diag.range.end.character);
                if (endPos >= 0) {
                    fix.edit.insert(document.uri, new vscode.Position(diag.range.end.line, endPos), '|e');
                }
                actions.push(fix);
            }

            // Quick fix: wrap in {% if defined %}
            if (code === 'TWIG-UNDEFINED-VAR') {
                const fix = new vscode.CodeAction('Wrap in {% if defined %}', vscode.CodeActionKind.QuickFix);
                fix.diagnostics = [diag];
                fix.edit = new vscode.WorkspaceEdit();
                const line = document.lineAt(diag.range.start.line);
                fix.edit.insert(document.uri, new vscode.Position(diag.range.start.line, 0),
                    `{% if ${document.getText(diag.range)} is defined %}\n`);
                fix.edit.insert(document.uri, new vscode.Position(diag.range.end.line, line.text.length),
                    `\n{% endif %}`);
                actions.push(fix);
            }

            // Quick fix: disable rule
            if (code !== 'TWIG-PARSE-ERROR' && code !== 'TWIG-INTERNAL-ERROR') {
                const disable = new vscode.CodeAction(`Disable rule '${code}'`, vscode.CodeActionKind.QuickFix);
                disable.command = {
                    command: 'workbench.action.openSettings',
                    title: 'Disable Rule',
                    arguments: ['twigAnalyzer.disabledRules'],
                };
                disable.diagnostics = [diag];
                actions.push(disable);
            }
        }

        return actions;
    }
}

// ═══════════════════════════════════════════════════════════════════════
// 16. Document Highlight — matching {% if %} ↔ {% endif %}
// ═══════════════════════════════════════════════════════════════════════

const HIGHLIGHT_PAIRS: Record<string, string> = {
    block: 'endblock', endblock: 'block',
    'for': 'endfor', endfor: 'for',
    'if': 'endif', endif: 'if',
    macro: 'endmacro', endmacro: 'macro',
    apply: 'endapply', endapply: 'apply',
    autoescape: 'endautoescape', endautoescape: 'autoescape',
    embed: 'endembed', endembed: 'embed',
    cache: 'endcache', endcache: 'cache',
    deprecated: 'enddeprecated', enddeprecated: 'deprecated',
    guard: 'endguard', endguard: 'guard',
    sandbox: 'endsandbox', endsandbox: 'sandbox',
    set: 'endset', endset: 'set',
    verbatim: 'endverbatim', endverbatim: 'verbatim',
    with: 'endwith', endwith: 'with',
};

export class TwigHighlightProvider implements vscode.DocumentHighlightProvider {
    provideDocumentHighlights(
        document: vscode.TextDocument,
        position: vscode.Position,
    ): vscode.ProviderResult<vscode.DocumentHighlight[]> {
        const wordRange = document.getWordRangeAtPosition(position, /\w+/);
        if (!wordRange) return [];
        const word = document.getText(wordRange);
        const pair = HIGHLIGHT_PAIRS[word];
        if (!pair) return [];

        const highlights: vscode.DocumentHighlight[] = [];
        highlights.push(new vscode.DocumentHighlight(wordRange, vscode.DocumentHighlightKind.Read));

        // Find matching pair
        const pattern = new RegExp(`\\{%-?\\s*${pair}\\b`, 'g');
        for (let i = 0; i < document.lineCount; i++) {
            const line = document.lineAt(i).text;
            let match: RegExpExecArray | null;
            while ((match = pattern.exec(line)) !== null) {
                const start = match.index + match[0].indexOf(pair);
                const r = new vscode.Range(i, start, i, start + pair.length);
                highlights.push(new vscode.DocumentHighlight(r, vscode.DocumentHighlightKind.Text));
            }
        }

        return highlights;
    }
}

// ═══════════════════════════════════════════════════════════════════════
// 17. Rename Provider — rename blocks/macros (F2)
// ═══════════════════════════════════════════════════════════════════════

export class TwigRenameProvider implements vscode.RenameProvider {
    provideRenameEdits(
        document: vscode.TextDocument,
        position: vscode.Position,
        newName: string,
    ): vscode.ProviderResult<vscode.WorkspaceEdit> {
        const wordRange = document.getWordRangeAtPosition(position, /\w+/);
        if (!wordRange) return null;
        const word = document.getText(wordRange);

        // Check context: is this in {% block NAME %} or {% endblock NAME %}?
        const line = document.lineAt(position).text;
        const isBlockName = /\{%-?\s*(?:block|endblock)\s+\w*$/.test(line.substring(0, position.character)) ||
                            /\{%-?\s*(?:macro|endmacro)\s+\w*$/.test(line.substring(0, position.character));

        if (!isBlockName) return null;

        const edit = new vscode.WorkspaceEdit();
        const pattern = new RegExp(`(\\{%-?\\s*(?:block|endblock)\\s+)${word}\\b`, 'g');

        for (let i = 0; i < document.lineCount; i++) {
            const lineText = document.lineAt(i).text;
            let match: RegExpExecArray | null;
            while ((match = pattern.exec(lineText)) !== null) {
                const start = match.index + match[1].length;
                const r = new vscode.Range(i, start, i, start + word.length);
                edit.replace(document.uri, r, newName);
            }
        }

        return edit;
    }

    prepareRename?(
        document: vscode.TextDocument,
        position: vscode.Position,
    ): vscode.ProviderResult<vscode.Range | { range: vscode.Range; placeholder: string }> {
        const wordRange = document.getWordRangeAtPosition(position, /\w+/);
        if (!wordRange) throw new Error('Cannot rename');
        const word = document.getText(wordRange);
        const line = document.lineAt(position).text;
        if (/\{%-?\s*(?:block|endblock|macro|endmacro)\s+\w*$/.test(line.substring(0, position.character))) {
            return wordRange;
        }
        throw new Error('Cannot rename');
    }
}

// ═══════════════════════════════════════════════════════════════════════
// 18. Color Provider — CSS color previews in Twig
// ═══════════════════════════════════════════════════════════════════════

export class TwigColorProvider implements vscode.DocumentColorProvider {
    provideDocumentColors(document: vscode.TextDocument): vscode.ProviderResult<vscode.ColorInformation[]> {
        const colors: vscode.ColorInformation[] = [];
        const hexRe = /#[0-9a-fA-F]{3,8}\b/g;
        const rgbRe = /rgb\(\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)\s*\)/g;
        const rgbaRe = /rgba\(\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)\s*,\s*([\d.]+)\s*\)/g;

        for (let i = 0; i < document.lineCount; i++) {
            const line = document.lineAt(i).text;
            
            for (const re of [hexRe, rgbRe]) {
                let match: RegExpExecArray | null;
                while ((match = re.exec(line)) !== null) {
                    const color = this.parseColor(match[0]);
                    if (color) {
                        const start = match.index;
                        const end = start + match[0].length;
                        colors.push(new vscode.ColorInformation(
                            new vscode.Range(i, start, i, end), color,
                        ));
                    }
                }
            }
        }
        return colors;
    }

    provideColorPresentations(
        color: vscode.Color,
    ): vscode.ProviderResult<vscode.ColorPresentation[]> {
        const r = Math.round(color.red * 255);
        const g = Math.round(color.green * 255);
        const b = Math.round(color.blue * 255);
        return [{ label: `#${r.toString(16).padStart(2, '0')}${g.toString(16).padStart(2, '0')}${b.toString(16).padStart(2, '0')}` }];
    }

    private parseColor(text: string): vscode.Color | undefined {
        if (text.startsWith('#')) {
            const h = text.substring(1);
            if (h.length === 3) {
                return new vscode.Color(
                    parseInt(h[0]+h[0], 16) / 255,
                    parseInt(h[1]+h[1], 16) / 255,
                    parseInt(h[2]+h[2], 16) / 255, 1,
                );
            }
            if (h.length === 6) {
                return new vscode.Color(
                    parseInt(h.substring(0,2), 16) / 255,
                    parseInt(h.substring(2,4), 16) / 255,
                    parseInt(h.substring(4,6), 16) / 255, 1,
                );
            }
            if (h.length === 8) {
                return new vscode.Color(
                    parseInt(h.substring(0,2), 16) / 255,
                    parseInt(h.substring(2,4), 16) / 255,
                    parseInt(h.substring(4,6), 16) / 255,
                    parseInt(h.substring(6,8), 16) / 255,
                );
            }
        }
        if (text.startsWith('rgb')) {
            const m = text.match(/[\d.]+/g);
            if (m && m.length >= 3) {
                return new vscode.Color(
                    parseInt(m[0]) / 255, parseInt(m[1]) / 255, parseInt(m[2]) / 255,
                    m.length >= 4 ? parseFloat(m[3]) : 1,
                );
            }
        }
        return undefined;
    }
}
