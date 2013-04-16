# -*- coding: utf-8 -*-
##
## This file is part of Invenio.
## Copyright (C) 2013 CERN.
##
## Invenio is free software; you can redistribute it and/or
## modify it under the terms of the GNU General Public License as
## published by the Free Software Foundation; either version 2 of the
## License, or (at your option) any later version.
##
## Invenio is distributed in the hope that it will be useful, but
## WITHOUT ANY WARRANTY; without even the implied warranty of
## MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU
## General Public License for more details.
##
## You should have received a copy of the GNU General Public License
## along with Invenio; if not, write to the Free Software Foundation, Inc.,
## 59 Temple Place, Suite 330, Boston, MA 02111-1307, USA.

"""
Invenio template migration engine.

Migrates output formats and output templates found in
CFG_BIBFORMAT_OUTPUTS_PATH and CFG_BIBFORMAT_TEMPLATES_PATH respectively.
It creates backup of each output format with name `<FORMAT>_legacy.bfo` and
generates new Jinja2 templates in CFG_BIBFORMAT_JINJA_TEMPLATE_PATH.
"""

import os
import shutil
from flask.ext.script import Manager

manager = Manager(usage="Perform migration operations")


@manager.option('--rewrite-existing-templates',
                dest='rewrite_existing_templates',
                action='store_true', default=False)
@manager.option('--verbose', dest='verbose')
def bft2tpl(rewrite_existing_templates=False, verbose=0):
    """Converts bft templates to Jinja2 templates."""

    ## Import all invenio modules inside to avoid side-efects ouside
    ## Flask application context.
    from invenio.bibformat_config import CFG_BIBFORMAT_OUTPUTS_PATH, \
        CFG_BIBFORMAT_FORMAT_OUTPUT_EXTENSION, \
        CFG_BIBFORMAT_FORMAT_TEMPLATE_EXTENSION, \
        CFG_BIBFORMAT_FORMAT_JINJA_TEMPLATE_EXTENSION, \
        CFG_BIBFORMAT_JINJA_TEMPLATE_PATH
    from invenio.bibformat_engine import get_format_element, \
        get_output_formats, \
        pattern_function_params, \
        pattern_tag, pattern_lang, \
        translation_pattern, \
        ln_pattern, get_format_templates
    from invenio.bibformatadminlib import update_output_format_rules

    def rename_template(template):
        if template[-3:] == CFG_BIBFORMAT_FORMAT_TEMPLATE_EXTENSION:
            return template[:-3] + \
                CFG_BIBFORMAT_FORMAT_JINJA_TEMPLATE_EXTENSION
        return template

    def update_rule(rule):
        rule['template'] = rename_template(rule['template'])
        print '        ...', rule['template'], 'to',
        print rename_template(rule['template'])
        print '           ', rule
        return rule

    def eval_format_template_elements(format_template, bfo, verbose=0):

        def insert_element_code(match):
            error = []
            function_name = match.group("function_name")
            try:
                format_element = get_format_element(function_name, verbose)
            except Exception:
                error.append('Invalid function name %s' % (function_name, ))

            params_str = []
            if format_element is not None:
                params = {}
                # Look for function parameters given in format template code
                all_params = match.group('params')
                if all_params is not None:
                    function_params_iterator = pattern_function_params.\
                        finditer(all_params)
                    for param_match in function_params_iterator:
                        sep = param_match.group('sep')
                        name = param_match.group('param')
                        value = param_match.group('value')
                        params[name] = value
                        params_str.append(name + '=' + sep + value + sep)

                # Replace element with function call with params.
                result = '{{ bfe_%s(bfo, %s) }}' % (function_name.lower(),
                                                    ', '.join(params_str))
                return result

            print '\n'.join(error)

        # Substitute special tags in the format by our own text.
        # Special tags have the form <BFE_format_element_name [param="value"]* />
        format = pattern_tag.sub(insert_element_code, format_template)
        return format

    def translate(match):
        """
        Translate matching values
        """
        word = match.group("word")
        translated_word = '{{ _("' + word + '") }}'
        return translated_word

    def filter_languages(format_template):

        def search_lang_tag(match):
            """
            Searches for the <lang>...</lang> tag.
            """
            ln_tags = {}

            def clean_language_tag(match):
                """
                Return tag text content if tag language of match is output
                language. Called by substitution in 'filter_languages(...)'

                @param match: a match object corresponding to the special tag
                              that must be interpreted
                """
                ln_tags[match.group(1)] = match.group(2)
                return '{% if g.ln == "' + match.group(1) + '" %}' + \
                    match.group(2) + '{% endif %}'

                # End of clean_language_tag

            lang_tag_content = match.group("langs")
            return '{% lang %}' + lang_tag_content + '{% endlang %}'
            cleaned_lang_tag = ln_pattern.sub(clean_language_tag,
                                              lang_tag_content)
            # FIXME no traslation for current language
            #if len(ln_tags) > 0:
            #    cleaned_lang_tag += '{% if not g.ln in ["' + \
            #        '", "'.join(ln_tags.keys()) + '"] %}' + \
            #        ln_tags.get(CFG_SITE_LANG, '') + '{% endif %}'
            return cleaned_lang_tag
            # End of search_lang_tag

        filtered_format_template = pattern_lang.sub(search_lang_tag,
                                                    format_template)
        return filtered_format_template

    skip_xsl = lambda (name, key): name[-3:] != 'xsl'
    format_templates = filter(skip_xsl, get_format_templates(True).iteritems())

    print '>>> Going to migrate %d format template(s) ...' % (
        len(format_templates), )

    if not os.path.exists(CFG_BIBFORMAT_JINJA_TEMPLATE_PATH):
        os.makedirs(CFG_BIBFORMAT_JINJA_TEMPLATE_PATH)

    for name, template in format_templates:

        new_name = os.path.join(CFG_BIBFORMAT_JINJA_TEMPLATE_PATH,
                                rename_template(name))

        if os.path.exists(new_name):
            print '    [!] File', new_name, 'already exists.',
            if not rewrite_existing_templates:
                print 'Skipped.'
                continue
            else:
                shutil.copy2(new_name, new_name + '.backup')
                print 'Rewritten.'

        print '    ... migrating', name, 'to', new_name

        with open(new_name, 'w+') as f:
            code = template['code']
            ln_tags_format = filter_languages(code)
            localized_format = translation_pattern.sub(translate,
                                                       ln_tags_format)
            evaled = eval_format_template_elements(localized_format, None)
            f.write(evaled)

    print

    skip_legacy = lambda (name, key): name[-11:] != '_legacy.' + \
        CFG_BIBFORMAT_FORMAT_OUTPUT_EXTENSION
    output_formats = filter(skip_legacy,
                            get_output_formats(with_attributes=True).
                            iteritems())
    print '>>> Going to migrate %d output format(s) ...' % (
        len(output_formats))

    for name, output_format in output_formats:
        if not any(map(lambda rule: rule['template'][-3:] == CFG_BIBFORMAT_FORMAT_TEMPLATE_EXTENSION,
                   output_format['rules'])):
            print '    [!]', name, 'does not contain any',
            print CFG_BIBFORMAT_FORMAT_TEMPLATE_EXTENSION, 'template.'
            continue

        new_name = name[:-4] + \
            '_legacy.' + CFG_BIBFORMAT_FORMAT_OUTPUT_EXTENSION
        if os.path.exists(os.path.join(CFG_BIBFORMAT_OUTPUTS_PATH, new_name)):
            print '    [!] File', new_name, 'already exists. Skipped.'
            continue
        shutil.copy2(
            os.path.join(CFG_BIBFORMAT_OUTPUTS_PATH, name),
            os.path.join(CFG_BIBFORMAT_OUTPUTS_PATH, new_name))
        # rename template names
        print '    ... migrating', name, 'to', new_name
        update_output_format_rules(name,
                                   map(update_rule, output_format['rules']),
                                   rename_template(output_format['default']))

    print
    print '>>> Please re-run `bibreformat` for all cached output formats.'
    print '    $ bibreformat -oHB,HD -a'


def main():
    from invenio.webinterface_handler_flask import create_invenio_flask_app
    app = create_invenio_flask_app()
    manager.app = app
    manager.run()

if __name__ == '__main__':
    main()
