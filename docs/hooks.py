
from pygments import highlight
from pygments.lexers import PythonLexer, HtmlLexer
from pygments.formatters import HtmlFormatter
from bs4 import BeautifulSoup

languages = {
    "python": PythonLexer(),
    "html": HtmlLexer(),
    "text": HtmlLexer(),
}

def highlight_code(file_name, page_state, _, page_contents):
    print(f"Checking {file_name}")
    if ".txt" in file_name or ".xml" in file_name:
        return page_contents
    print(f"Highlighting code in {file_name}")
    soup = BeautifulSoup(page_contents, 'lxml')

    for pre in soup.find_all('pre'):
        code = pre.find('code')
        try:
            language = code['class'][0].split("language-")[1]
            code = highlight(code.text, languages[language], HtmlFormatter())
        except:
            continue
        
        pre.replace_with(BeautifulSoup(code, 'html.parser'))

    css = HtmlFormatter().get_style_defs('.highlight')
    css = f"<style>{css}</style>"

    # this happens for bookmarks
    if not soup.find("body"):
        return ""
    
    body = soup.find('body')
    body.insert(0, BeautifulSoup(css, 'html.parser'))

    return str(soup)