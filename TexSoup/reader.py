"""Parsing mechanisms should not be directly invoked publicly, as they are
subject to change."""

from TexSoup.utils import Token, Buffer, MixedBuffer, CharToLineOffset
from TexSoup.data import *
from TexSoup.tokens import (
    TC,
    tokenize,
    ARG_START_TOKENS,
    ARG_END_TOKENS,
    SKIP_ENVS,
)
import string


__all__ = ['read_expr', 'read_tex']


def read_tex(buf, skip_envs=()):
    r"""Parse all expressions in buffer

    :param Buffer buf: a buffer of tokens
    :param Tuple[str] skip_envs: environments to skip parsing
    :return: Iterable[TexExpr]
    """
    buf = Buffer(read_exprs(buf, read_skip, skip_envs=skip_envs))
    buf = MixedBuffer(read_exprs(buf, read_expr))
    buf = read_exprs(buf, wrap_expr)
    return buf


def read_exprs(buf, read, **kwargs):
    while buf.hasNext():
        yield read(buf, **kwargs)


def read_skip(src, skip_envs=()):
    r"""Group skipped envs into single token.

    :param Buffer src: a buffer of tokens
    :param Tuple[str] skip_envs: environments to skip parsing
    :return: Token

    >>> from TexSoup.category import categorize
    >>> from TexSoup.tokens import tokenize
    >>> buf = tokenize(categorize(r'\begin{foobar} \textbf{aa \end{foobar}'))
    >>> read_skip(buf, skip_envs=('foobar',)).category
    <TokenCode.Skip: 41>
    """
    c = next(src)
    position = src.position  # grab position before advancing buffer

    if c.category == TC.Escape and src.peek() == 'begin':
        name, args, steps = peek_command(src, n_required_args=1)
        if args[0].string in skip_envs:
            token = Token(src.forward(steps), position)
            token += src.forward_until(lambda s:
                s.startswith(r'\\end{%s}' % name), peek=False)
            token += src.forward(3)
            token.category = TC.Skip
            return token
    return c


def read_expr(src, context=None):
    r"""Read next expression from buffer

    :param Buffer src: a buffer of tokens
    :param TexExpr context: parent expression
    :return: [TexExpr, Token]
    """
    c = next(src)
    # TODO: assemble and use groups
    if c.category == TC.MathSwitch:
        expr = TexEnv(c, begin=c, end=c, contents=[])
        return read_math_env(src, expr)
    elif c.category == TC.MathGroupStart:
        if c.startswith(TexDisplayMathEnv.begin):
            expr = TexDisplayMathEnv([])
        else:
            expr = TexMathEnv([])
        return read_math_env(src, expr)
    elif c.category == TC.Escape:
        # TODO: reduce to command-parsing only -- assemble envs in 2nd pass
        name, args, steps = peek_command(src, n_required_args=1)
        if name == 'item':
            contents, arg = read_item(src)
            expr = TexCmd(name, contents, arg)
        elif name == 'begin':
            assert args, 'Begin command must be followed by an env name.'
            expr = TexNamedEnv(args[0].string)
            expr.args = args[1:]
            src.forward(steps)
            read_env(src, expr)
        else:
            src.forward(1)
            expr = TexCmd(name)
            expr.args = read_args(src, expr.args)
        return expr
    if c.category == TC.OpenBracket and isinstance(context, TexArgs) or \
            c.category == TC.GroupStart:
        return read_arg(src, c)

    assert isinstance(c, Token)
    return c


def wrap_expr(src):
    """Wrap next expression in buffer with TexExpr object if still a token

    :param Buffer src: a buffer of tokens
    :return: TexExpr
    """
    c = next(src)
    if isinstance(c, Token):
        return TexText(c)
    return c


def stringify(string):
    return Token.join(string.split(' '), glue=' ')


def read_item(src):
    r"""Read the item content. Assumes escape has just been parsed.

    There can be any number of whitespace characters between \item and the
    first non-whitespace character. Any amount of whitespace between subsequent
    characters is also allowed.

    \item can also take an argument.

    :param Buffer src: a buffer of tokens
    :return: contents of the item and any item arguments

    >>> from TexSoup.category import categorize
    >>> from TexSoup.tokens import tokenize
    >>> def read_item_from(string, skip=1):
    ...     buf = tokenize(categorize(string))
    ...     _ = buf.forward(skip)
    ...     return read_item(buf)
    >>> read_item_from(r'\item aaa {bbb} ccc\end{itemize}')
    (['aaa ', BraceGroup('bbb'), ' ccc'], [])
    >>> read_item_from(r'\item aaa \textbf{itemize}\item no')
    (['aaa ', TexCmd('textbf', [BraceGroup('itemize')])], [])
    >>> read_item_from(r'\item[aaa] yith\item no')
    (['yith'], [BracketGroup('aaa')])
    >>> read_item_from('\\item\n[aaa] yith\\item no')
    (['yith'], [BracketGroup('aaa')])
    >>> read_item_from(r'\item WITCH [nuuu] DOCTORRRR 👩🏻‍⚕️')
    (['WITCH ', '[', 'nuuu', ']', ' DOCTORRRR 👩🏻‍⚕️'], [])
    >>> read_item_from(r'''\begin{itemize}
    ... \item
    ... \item first item
    ... \end{itemize}''', skip=7)
    ([], [])
    """
    assert next(src) == 'item'
    args, extras = [], []

    # TODO: fix when spacer tokenization updated
    spacer, rest = read_spacer(src)
    if rest:
        extras.append(rest)

    # TODO: use peek_command instead of manually parsing optional arg
    if not rest and src.hasNext() and src.peek().category == TC.OpenBracket:
        c = next(src)
        args.append(read_arg(src, c))

        # remove leading spacer after arguments, due to quirk in Item repr
        # which adds space after args.
        spacer, rest = read_spacer(src)
        if rest:
            extras.append(rest)

    while src.hasNext():
        if src.peek().category == TC.Escape:
            cmd_name, cmd_args, steps = peek_command(src, 1, skip=1)
            if cmd_name in ('end', 'item'):
                return extras, args
        extras.append(read_expr(src))
    return extras, args


def read_math_env(src, expr):
    r"""Read the environment from buffer.

    Advances the buffer until right after the end of the environment. Adds
    parsed content to the expression automatically.

    :param Buffer src: a buffer of tokens
    :param TexExpr expr: expression for the environment
    :rtype: TexExpr
    """
    content = src.forward_until(lambda s: s.startswith(expr.end), peek=False)
    if not src.startswith(expr.end):
        end = src.peek()
        explanation = 'Instead got %s' % end if end else 'Reached end of file.'
        raise EOFError('Expecting %s. %s' % (expr.end, explanation))
    else:
        next(src)
    expr.append(content)
    return expr


def read_env(src, expr, skip_envs=()):
    r"""Read the environment from buffer.

    Advances the buffer until right after the end of the environment. Adds
    parsed content to the expression automatically.

    :param Buffer src: a buffer of tokens
    :param TexExpr expr: expression for the environment
    :rtype: TexExpr
    """
    contents = []
    if expr.name in SKIP_ENVS + skip_envs:
        contents = [src.forward_until(
            lambda s: s.startswith('\\end'), peek=False)]
    while src.hasNext() and not src.startswith('\\end{%s}' % expr.name):
        contents.append(read_expr(src))
    if not src.startswith('\\end{%s}' % expr.name):
        end = src.peek((0, 6))
        explanation = 'Instead got %s' % end if end else 'Reached end of file.'
        raise EOFError('Expecting \\end{%s}. %s' % (expr.name, explanation))
    else:
        src.forward(5)
    expr.append(*contents)
    return expr


def read_args(src, args=None):
    r"""Read all arguments from buffer.

    Advances buffer until end of last valid arguments. There can be any number
    of whitespace characters between command and the first argument.
    However, after that first argument, the command can only tolerate one
    successive line break, before discontinuing the chain of arguments.

    :param TexArgs args: existing arguments to extend
    :return: parsed arguments
    :rtype: TexArgs
    """
    args = args or TexArgs()

    # Unlimited whitespace before first argument
    candidate_index = src.num_forward_until(lambda s: not s.isspace())
    while src.hasNext() and src.peek().isspace():
        args.append(read_expr(src, context=args))

    # Restricted to only one line break after first argument
    line_breaks = 0
    while src.hasNext() and src.peek().category in ARG_START_TOKENS or \
            (src.hasNext() and src.peek().isspace() and line_breaks == 0):
        space_index = src.num_forward_until(lambda s: not s.isspace())
        if space_index > 0:
            line_breaks += 1
            if src.peek((0, space_index)).count("\n") <= 1 \
                    and src.peek(space_index) is not None \
                    and src.peek(space_index).category in ARG_START_TOKENS:
                args.append(read_expr(src, context=args))
        else:
            line_breaks = 0
            tex_text = read_expr(src, context=args)
            args.append(tex_text)

    if not args:
        src.backward(candidate_index)

    return args


def read_arg(src, c):
    """Read the argument from buffer.

    Advances buffer until right before the end of the argument.

    :param Buffer src: a buffer of tokens
    :param str c: argument token (starting token)
    :return: the parsed argument
    :rtype: TexGroup
    """
    content = [c]
    while src.hasNext():
        if src.peek().category in ARG_END_TOKENS:
            content.append(next(src))
            break
        else:
            content.append(read_expr(src))
    return TexGroup.parse(content)


# TODO: move spacer tokenization to tokenizer
# WARNING: This method is flawed: Spacer detection only works for first
# instance of spacer in text. Will need to refactor generic string tokenization
# which can only occur after refactoring item, arg, and env readers above,
# which in turn, rely on the skip_env reader.
def read_spacer(buf):
    r"""Extracts the next spacer, if there is one, before non-whitespace

    Define a spacer to be a contiguous string of only whitespace, with at most
    one line break.

    >>> from TexSoup.category import categorize
    >>> from TexSoup.tokens import tokenize
    >>> read_spacer(Buffer(tokenize(categorize('   \t    \n'))))
    ('   \t    \n', '')
    >>> read_spacer(Buffer(tokenize(categorize('   \t    \n\t \n  \t\n'))))
    ('   \t    \n\t ', '\n  \t\n')
    >>> read_spacer(Buffer(tokenize(categorize('{'))))
    ('', '')
    >>> read_spacer(Buffer(tokenize(categorize('   \t    \na'))))
    ('   \t    \n', 'a')
    >>> read_spacer(Buffer(tokenize(categorize('   \t    \n\t \n  \t\na'))))
    ('   \t    \n\t ', '\n  \t\na')
    """
    if not buf.hasNext() or not buf.peek().category == TC.Text:
        return '', ''

    text, lines = next(buf), 1
    spacer, rest, is_spacer = '', '', True
    for c in text:
        if c == '\n':  # TODO: change to token code
            lines += 1
        if is_spacer and lines > 2 or not c.isspace():
            is_spacer = False
        if is_spacer:
            spacer += c
        else:
            rest += c

    return spacer, rest


# TODO: refactor after generic string tokenizer fixed
# TODO: hard-coded to 1 required arg
def peek_command(buf, n_required_args=-1, n_optional_args=-1, skip=0):
    r"""Parses command and all arguments. Assumes escape has just been parsed.

    Here are rules for command name and argument parsing:

    1. No whitespace is allowed between escape and command name. e.g., \ textbf
       is the "command" "\" and the text "textbf". Only \textbf is the bold
       command.
    2. One spacer is allowed between the command name and the first argument,
       optional or required.
    3. If command has 1 required argument and the command name is followed by a
       a spacer, the first character after that spacer is used as the first
       argument. This first character can be a line break OR a non-whitespace
       character. The same applies for all subsequent required arguments: The
       first character after an optional spacer is used.

    >>> from TexSoup.category import categorize
    >>> from TexSoup.tokens import tokenize
    >>> buf = Buffer(tokenize(categorize('\section   \t    \n\t{wallawalla}')))
    >>> next(buf)
    '\\'
    >>> peek_command(buf)
    ('section', [BraceGroup('wallawalla')], 5)
    >>> buf = Buffer(tokenize(categorize('\section   \t    \n\t \n{bingbang}')))
    >>> _ = next(buf)
    >>> peek_command(buf)
    ('section', [], 2)
    >>> buf = Buffer(tokenize(categorize('\section{ooheeeee}')))
    >>> _ = next(buf)
    >>> peek_command(buf)
    ('section', [BraceGroup('ooheeeee')], 4)

    # Broken because abcd is incorrectly tokenized with leading space
    # >>> buf = Buffer(tokenize(categorize('\section abcd')))
    # >>> _ = next(buf)
    # >>> peek_command(buf)
    # ('section', ('a',), 2)
    """
    position = buf.position
    for _ in range(skip):
        next(buf)

    token, name, args = Token('', buf.position), next(buf), TexArgs()

    spacer, rest = read_spacer(buf)
    if not rest:
        token += spacer  # TODO: category = TC.Spacer; TODO: use token?

        if buf.hasNext() and buf.peek().category == TC.GroupStart:
            args = read_args(buf, args=args)

    steps = buf.position - position
    buf.backward(steps)
    return name, args, steps
