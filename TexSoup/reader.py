"""Parsing mechanisms should not be directly invoked publicly, as they are
subject to change."""

from TexSoup.category import categorize
from TexSoup.utils import Token, Buffer, MixedBuffer, CharToLineOffset
from TexSoup.data import *
from TexSoup.data import arg_type
from TexSoup.tokens import (
    TC,
    tokenize,
    SKIP_ENV_NAMES,
    MATH_ENV_NAMES,
)
from TexSoup.dynamic_tracker import ParentTracker
from TexSoup.dynamic_tracker import GroupTracker
from TexSoup.dynamic_tracker import CustomDefs, CustomMacro
from TexSoup.dynamic_tracker import MacroSignatures

import functools
import string
import sys
import collections as coll
import itertools as itr
import re

SKIP_MATH = True
EXPAND_MACROS = False
MODE_MATH = 'mode:math'
MODE_NON_MATH = 'mode:non-math'
MATH_SIMPLE_ENVS = (
    TexDisplayMathModeEnv,
    TexMathModeEnv,
    TexDisplayMathEnv,
    TexMathEnv
)
MATH_TOKEN_TO_ENV = {env.token_begin: env for env in MATH_SIMPLE_ENVS}
ARG_BEGIN_TO_ENV = {arg.token_begin: arg for arg in arg_type}

DEF_MACROS = {
    'renewcommand': set([0]),
    'newcommand': set([0, 3]),
}



__all__ = ['read_expr', 'read_tex']

def sub_macro(name, args):
    macro_def = CustomDefs.macros_dict.get(name, None)
    assert macro_def is not None, f"Custom macro {name} is not defined"
    # num_args=(req_args, opt_args),
    # name=cmd_name, 
    # default_val=default_val,
    # def_fmt_str=def_fmt_str,
    arg_dict = {}
    arg_counter = 1 
    if len(args) < sum(macro_def.num_args):
        arg_dict[f'pyarg_{arg_counter}'] = macro_def.default_val
        arg_counter += 1
    for arg in args:
        arg_dict[f'pyarg_{arg_counter}'] = arg.string
        arg_counter += 1
    expanded_macro_string = macro_def.def_fmt_str.format(**arg_dict)
    return expanded_macro_string


def update_signatures(expr):
    """Update the function signatures as new functions are defined

    :param expr TexExpr
    """
    if not hasattr(expr, "name"):
        return
    if not (expr.name == "newcommand" and expr.args):
        return
    
    cmd_name = None
    req_args = 0
    opt_args = 0
    default_val = None
    def_fmt_str = None

    if isinstance(expr.args[0], BraceGroup):
        cmd_elem = expr.args[0]._contents[0]
        if isinstance(cmd_elem, str): 
            cmd_name = cmd_elem.strip("\\")
        elif hasattr(cmd_elem, 'name'):
            cmd_name = cmd_elem.name
    if isinstance(expr.args[0], TexCmd):
        cmd_name = expr.args[0].name
    if not cmd_name:
       sys.stderr.write(f"Cmd name not recognized in {expr}.\n")
       return

    if len(expr.args) > 2:
        if isinstance(expr.args[1], BracketGroup):
            req_args = int(expr.args[1]._contents[0])
    if len(expr.args) > 3:
        if isinstance(expr.args[2], BracketGroup):
            opt_args = 1
            default_val = expr.args[2].contents[0].string
    req_args = req_args - opt_args
    MacroSignatures.sig_dict[cmd_name] = (req_args, opt_args)

    definition = expr.args[-1].string

    pat = re.compile(r"(?<!#)#([0-9]+)")
    def_fmt_str = re.sub(
        pat, 
        lambda match: f"{{pyarg_{match.group(1)}}}",
        definition.replace('{', "{{").replace('}', "}}"))

    new_macro = CustomMacro(
        name=cmd_name, 
        num_args=(req_args, opt_args),
        default_val=default_val,
        def_fmt_str=def_fmt_str,
    )
    CustomDefs.macros_dict[cmd_name] = new_macro

    

def read_tex(buf, skip_envs=(), tolerance=0):
    r"""Parse all expressions in buffer

    :param Buffer buf: a buffer of tokens
    :param Tuple[str] skip_envs: environments to skip parsing
    :param int tolerance: error tolerance level (only supports 0 or 1)
    :return: iterable over parsed expressions
    :rtype: Iterable[TexExpr]
    """
    while buf.hasNext():
        expr = read_expr(buf,
                        skip_envs=SKIP_ENV_NAMES + skip_envs,
                        tolerance=tolerance)
        # update signatures for newly discovered commands
        update_signatures(expr)
        yield expr


def make_read_peek(f):
    r"""Make any reader into a peek function.

    The wrapped function still parses the next sequence of tokens in the
    buffer but rolls back the buffer position afterwards.

    >>> from TexSoup.category import categorize
    >>> from TexSoup.tokens import tokenize
    >>> def read(buf):
    ...     buf.forward(3)
    >>> buf = Buffer(tokenize(categorize(r'\item testing \textbf{hah}')))
    >>> buf.position
    0
    >>> make_read_peek(read)(buf)
    >>> buf.position
    0
    """
    @functools.wraps(f)
    def wrapper(buf, *args, **kwargs):
        #old_queue = buf._Buffer__queue.copy()
        start = buf.position
        ret = f(buf, *args, **kwargs)
        #new_queue = buf._Buffer__queue
        buf.backward(buf.position - start)
        return ret
    return wrapper


def read_expr(src, skip_envs=(), tolerance=0, mode=MODE_NON_MATH, is_arg=False, arg_end=None):
    r"""Read next expression from buffer

    :param Buffer src: a buffer of tokens
    :param Tuple[str] skip_envs: environments to skip parsing
    :param int tolerance: error tolerance level (only supports 0 or 1)
    :param str mode: math or not math mode
    :return: parsed expression
    :rtype: [TexExpr, Token]
    """
    c = next(src)
    if (not is_arg) and c.category in MATH_TOKEN_TO_ENV.keys():
        expr = MATH_TOKEN_TO_ENV[c.category]([], position=c.position)
        if SKIP_MATH:
            return read_skip_math_env(src, expr, tolerance=tolerance)
        return read_math_env(src, expr, tolerance=tolerance)
    elif c.category == TC.Escape:

        # name, 0
        parent_offset = 1
        if len(ParentTracker.stack) >= parent_offset:
            parent_name, arg_found = ParentTracker.stack[-parent_offset]  #second to top stack item
        else:
            parent_name, arg_found = None, None
        if parent_name in DEF_MACROS and arg_found in DEF_MACROS[parent_name]:
            name, args = read_command(src, n_required_args=0, n_optional_args=0, tolerance=tolerance, mode=mode)
        else:
            name, args = read_command(src, tolerance=tolerance, mode=mode)
        if EXPAND_MACROS and name in CustomDefs.macros_dict and parent_name not in DEF_MACROS:
            res_string = sub_macro(name, args)
            tokens = tokenize(categorize(res_string))
            src.prepend(tokens, pop=[c, name])
            return
        elif name == 'item':
            assert mode != MODE_MATH, r'Command \item invalid in math mode.'
            contents = read_item(src)
            expr = TexCmd(name, contents, args, position=c.position)
        elif arg_end and src.peek().category == arg_end:
            expr = TexCmd(name, args=args, position=c.position)
        elif name == 'begin':
            assert args, 'Begin command must be followed by an env name.'
            expr = TexNamedEnv(
                args[0].string, args=args[1:], position=c.position)
            expr = get_named_env(
                src, expr, 
                skip_envs=skip_envs,
                tolerance=tolerance, is_arg=is_arg
            )
        else:
            expr = TexCmd(name, args=args, position=c.position)
        return expr
    if c.category == TC.GroupBegin:
        return read_arg(src, c, tolerance=tolerance)

    assert isinstance(c, Token)
    return TexText(c)

def get_named_env(src, expr, skip_envs=(), tolerance=0, is_arg=False, mode=MODE_NON_MATH):
    if expr.name in MATH_ENV_NAMES:
        mode = MODE_MATH
    if is_arg or (expr.name in skip_envs):
        read_skip_env(src, expr, is_arg)
    else:
        read_env(src, expr, skip_envs=skip_envs,tolerance=tolerance, mode=mode)
    return expr



################
# ENVIRONMENTS #
################


def read_item(src, tolerance=0):
    r"""Read the item content. Assumes escape has just been parsed.

    There can be any number of whitespace characters between \item and the
    first non-whitespace character. Any amount of whitespace between subsequent
    characters is also allowed.

    \item can also take an argument.

    :param Buffer src: a buffer of tokens
    :param int tolerance: error tolerance level (only supports 0 or 1)
    :return: contents of the item and any item arguments

    >>> from TexSoup.category import categorize
    >>> from TexSoup.tokens import tokenize
    >>> def read_item_from(string, skip=2):
    ...     buf = tokenize(categorize(string))
    ...     _ = buf.forward(skip)
    ...     return read_item(buf)
    >>> read_item_from(r'\item aaa {bbb} ccc\end{itemize}')
    [' aaa ', BraceGroup('bbb'), ' ccc']
    >>> read_item_from(r'\item aaa \textbf{itemize}\item no')
    [' aaa ', TexCmd('textbf', [BraceGroup('itemize')])]
    >>> read_item_from(r'\item WITCH [nuuu] DOCTORRRR 👩🏻‍⚕️')
    [' WITCH ', '[', 'nuuu', ']', ' DOCTORRRR 👩🏻‍⚕️']
    >>> read_item_from(r'''\begin{itemize}
    ... \item
    ... \item first item
    ... \end{itemize}''', skip=8)
    ['\n']
    >>> read_item_from(r'''\def\itemeqn{\item}''', skip=7)
    []
    """
    extras = []

    while src.hasNext():
        if src.peek().category == TC.Escape:
            cmd_name, _ = make_read_peek(read_command)(
                src, 1, skip=1, tolerance=tolerance)
            if cmd_name in ('end', 'item'):
                return extras
        elif src.peek().category == TC.GroupEnd:
            #_ = GroupTracker.pop()
            break
        extras.append(read_expr(src, tolerance=tolerance))
    return extras


def unclosed_env_handler(src, expr, end):
    """Handle unclosed environments.

    Currently raises an end-of-file error. In the future, this can be the hub
    for unclosed-environment fault tolerance.

    :param Buffer src: a buffer of tokens
    :param TexExpr expr: expression for the environment
    :param int tolerance: error tolerance level (only supports 0 or 1)
    :param end str: Actual end token (as opposed to expected)
    """
    clo = CharToLineOffset(str(src))
    explanation = 'Instead got %s' % end if end else 'Reached end of file.'
    line, offset = clo(src.position)
    raise EOFError('[Line: %d, Offset: %d] "%s" env expecting %s. %s' % (
        line, offset, expr.name, expr.end, explanation))


def read_math_env(src, expr, tolerance=0):
    r"""Read the environment from buffer.

    Advances the buffer until right after the end of the environment. Adds
    parsed content to the expression automatically.

    :param Buffer src: a buffer of tokens
    :param TexExpr expr: expression for the environment
    :rtype: TexExpr

    >>> from TexSoup.category import categorize
    >>> from TexSoup.tokens import tokenize
    >>> buf = tokenize(categorize(r'\min_x \|Xw-y\|_2^2'))
    >>> read_math_env(buf, TexMathModeEnv())
    Traceback (most recent call last):
        ...
    EOFError: [Line: 0, Offset: 7] "$" env expecting $. Reached end of file.
    """
    contents = []
    while src.hasNext() and src.peek().category != expr.token_end:
        contents.append(read_expr(src, tolerance=tolerance, mode=MODE_MATH))
        
    if not src.hasNext() or src.peek().category != expr.token_end:
        unclosed_env_handler(src, expr, src.peek())
    next(src)
    expr.append(*contents)
    return expr

def read_skip_math_env(src, expr, is_arg=False, tolerance=0):
    r"""Read the environment from buffer, WITHOUT parsing contents

    Advances the buffer until right after the end of the environment. Adds
    UNparsed content to the expression automatically.

    :param Buffer src: a buffer of tokens
    :param TexExpr expr: expression for the environment
    :rtype: TexExpr

    >>> from TexSoup.category import categorize
    >>> from TexSoup.tokens import tokenize
    >>> buf = tokenize(categorize(r' \textbf{aa \end{foobar}ha'))
    >>> read_skip_env(buf, TexNamedEnv('foobar'))
    TexNamedEnv('foobar', [' \\textbf{aa '], [])
    >>> buf = tokenize(categorize(r' \textbf{aa ha'))
    >>> read_skip_env(buf, TexNamedEnv('foobar'))  #doctest:+ELLIPSIS
    Traceback (most recent call last):
        ...
    EOFError: ...
    """
    contents = []
    while src.hasNext() and src.peek().category != expr.token_end:
        contents.append(src.forward(1))
    if not src.hasNext() or src.peek().category != expr.token_end:
            unclosed_env_handler(src, expr, src.peek())
    next(src)
    expr.append(*contents)
    return expr

def read_skip_env(src, expr, is_arg=False):
    r"""Read the environment from buffer, WITHOUT parsing contents

    Advances the buffer until right after the end of the environment. Adds
    UNparsed content to the expression automatically.

    :param Buffer src: a buffer of tokens
    :param TexExpr expr: expression for the environment
    :rtype: TexExpr

    >>> from TexSoup.category import categorize
    >>> from TexSoup.tokens import tokenize
    >>> buf = tokenize(categorize(r' \textbf{aa \end{foobar}ha'))
    >>> read_skip_env(buf, TexNamedEnv('foobar'))
    TexNamedEnv('foobar', [' \\textbf{aa '], [])
    >>> buf = tokenize(categorize(r' \textbf{aa ha'))
    >>> read_skip_env(buf, TexNamedEnv('foobar'))  #doctest:+ELLIPSIS
    Traceback (most recent call last):
        ...
    EOFError: ...
    """
    def condition(s): return s.startswith('\\end{%s}' % expr.name)
    contents = [src.forward_until(condition, peek=False)]
    if (not is_arg) and (not src.startswith('\\end{%s}' % expr.name)):
        unclosed_env_handler(src, expr, src.peek((0, 6)))
    src.forward(5)
    expr.append(*contents)
    return expr


def read_env(src, expr, skip_envs=(), tolerance=0, mode=MODE_NON_MATH):
    r"""Read the environment from buffer.

    Advances the buffer until right after the end of the environment. Adds
    parsed content to the expression automatically.

    :param Buffer src: a buffer of tokens
    :param TexExpr expr: expression for the environment
    :param int tolerance: error tolerance level (only supports 0 or 1)
    :param str mode: math or not math mode
    :rtype: TexExpr

    >>> from TexSoup.category import categorize
    >>> from TexSoup.tokens import tokenize
    >>> buf = tokenize(categorize(' tingtang \\end\n{foobar}walla'))
    >>> read_env(buf, TexNamedEnv('foobar'))
    TexNamedEnv('foobar', [' tingtang '], [])
    >>> buf = tokenize(categorize(' tingtang \\end\n\n{foobar}walla'))
    >>> read_env(buf, TexNamedEnv('foobar')) #doctest: +ELLIPSIS
    Traceback (most recent call last):
        ...
    EOFError: [Line: 0, Offset: 1] ...
    >>> buf = tokenize(categorize(' tingtang \\end\n\n{nope}walla'))
    >>> read_env(buf, TexNamedEnv('foobar'), tolerance=1)  # error tolerance
    TexNamedEnv('foobar', [' tingtang '], [])
    """
    contents = []
    while src.hasNext():
        if src.peek().category == TC.Escape:
            name, args = make_read_peek(read_command)(
                src, skip=1, tolerance=tolerance, mode=mode)
            if name == 'end':
                #name, args = read_command(src, skip=1, tolerance=tolerance, mode=mode)
                break

        next_expr = read_expr(src, skip_envs=skip_envs, tolerance=tolerance, mode=mode)
        if next_expr:
            contents.append(next_expr)
    error = not src.hasNext() or not args or args[0].string != expr.name
    if error and tolerance == 0:
        unclosed_env_handler(src, expr, src.peek((0, 6)))
    elif not error:
        ff=0
        while ff < 5: # 5 tokens
            cur_token = src.forward()
            if cur_token.category != TC.MergedSpacer:
                ff += 1
    expr.append(*contents)
    return expr


############
# COMMANDS #
############


# TODO: handle macro-weirdness e.g., \def\blah[#1][[[[[[[[#2{"#1 . #2"}
# TODO: add newcommand macro
def read_args(src, n_required=-1, n_optional=-1, args=None, tolerance=0,
        mode=MODE_NON_MATH):
    r"""Read all arguments from buffer.

    This function assumes that the command name has already been parsed. By
    default, LaTeX allows only up to 9 arguments of both types, optional
    and required. If `n_optional` is not set, all valid bracket groups are
    captured. If `n_required` is not set, all valid brace groups are
    captured.

    :param Buffer src: a buffer of tokens
    :param TexArgs args: existing arguments to extend
    :param int n_required: Number of required arguments. If < 0, all valid
                           brace groups will be captured.
    :param int n_optional: Number of optional arguments. If < 0, all valid
                           bracket groups will be captured.
    :param int tolerance: error tolerance level (only supports 0 or 1)
    :param str mode: math or not math mode
    :return: parsed arguments
    :rtype: TexArgs

    >>> from TexSoup.category import categorize
    >>> from TexSoup.tokens import tokenize
    >>> test = lambda s, *a, **k: read_args(tokenize(categorize(s)), *a, **k)
    >>> test('[walla]{walla}{ba]ng}')  # 'regular' arg parse
    [BracketGroup('walla'), BraceGroup('walla'), BraceGroup('ba', ']', 'ng')]
    >>> test('\t[wa]\n{lla}\n\n{b[ing}')  # interspersed spacers + 2 newlines
    [BracketGroup('wa'), BraceGroup('lla')]
    >>> test('\t[\t{a]}bs', 2, 0)  # use char as arg, since no opt args
    [BraceGroup('['), BraceGroup('a', ']')]
    >>> test('\n[hue]\t[\t{a]}', 2, 1)  # check stop opt arg capture
    [BracketGroup('hue'), BraceGroup('['), BraceGroup('a', ']')]
    >>> test('\t\\item')
    []
    >>> test('   \t    \n\t \n{bingbang}')
    []
    >>> test('[tempt]{ing}[WITCH]{doctorrrr}', 0, 0)
    []
    """
    args = args or TexArgs()
    if n_required == 0 and n_optional == 0:
        return args
    
    ## rewrote this part to accept {}[][]{}
    #attempts_max = max(1, n_required + n_optional)
    #attempts = 0
    #old_arg_count = n_required + n_optional
    while n_required != 0:
        old_arg_count = n_required + n_optional
        if src.hasNext():
            next_cat = src.peek().category
            #while next_cat == TC.MergedSpacer:
            #    src.forward()
            #    next_cat = src.peek().category
            if next_cat == TC.BracketBegin:
                n_optional = read_arg_optional(
                    src, args, n_optional, tolerance, mode
                )
            elif next_cat == TC.GroupBegin:
                n_required = read_arg_required(
                    src, args, n_required, tolerance, mode
                )
            elif next_cat == TC.GroupEnd and len(GroupTracker.stack):
                # pop and consume are done later
                # _ = GroupTracker.pop()
                #src.forward() # consume the group end
                break
            else:
                n_optional = read_arg_optional(src, args, n_optional, tolerance, mode)
                n_required = read_arg_required(src, args, n_required, tolerance, mode)
        #attempts += 1
        if (n_required + n_optional) == old_arg_count:
            break
    return args


def read_arg_optional(
        src, args, n_optional=-1, tolerance=0, mode=MODE_NON_MATH):
    """Read next optional argument from buffer.

    If the command has remaining optional arguments, look for:

       a. A spacer. Skip the spacer if it exists.
       b. A bracket delimiter. If the optional argument is bracket-delimited,
          the contents of the bracket group are used as the argument.

    :param Buffer src: a buffer of tokens
    :param TexArgs args: existing arguments to extend
    :param int n_optional: Number of optional arguments. If < 0, all valid
                           bracket groups will be captured.
    :param int tolerance: error tolerance level (only supports 0 or 1)
    :param str mode: math or not math mode
    :return: number of remaining optional arguments
    :rtype: int
    """
    while n_optional != 0:
        spacer = read_spacer(src)
        if not (src.hasNext() and src.peek().category == TC.BracketBegin):
            if spacer:
                src.backward(1)
            break
        args.append(read_arg(src, next(src), tolerance=tolerance, mode=mode))
        n_optional -= 1
    return n_optional


def read_arg_required(
        src, args, n_required=-1, tolerance=0, mode=MODE_NON_MATH):
    r"""Read next required argument from buffer.

    If the command has remaining required arguments, look for:

       a. A spacer. Skip the spacer if it exists.
       b. A curly-brace delimiter. If the required argument is brace-delimited,
          the contents of the brace group are used as the argument.
       c. Spacer or not, if a brace group is not found, simply use the next
          character, unless it is a backslash, in which case use the full command name

    :param Buffer src: a buffer of tokens
    :param TexArgs args: existing arguments to extend
    :param int n_required: Number of required arguments. If < 0, all valid
                           brace groups will be captured.
    :param int tolerance: error tolerance level (only supports 0 or 1)
    :param str mode: math or not math mode
    :return: number of remaining optional arguments
    :rtype: int

    >>> from TexSoup.category import categorize
    >>> from TexSoup.tokens import tokenize
    >>> buf = tokenize(categorize('{wal]la}\n{ba ng}\n'))
    >>> args = TexArgs()
    >>> read_arg_required(buf, args)  # 'regular' arg parse
    -3
    >>> args
    [BraceGroup('wal', ']', 'la'), BraceGroup('ba ng')]
    >>> buf.hasNext() and buf.peek().category == TC.MergedSpacer
    True
    """
    while n_required != 0 and src.hasNext():
        spacer = read_spacer(src)

        if src.hasNext() and (src.peek().category == TC.GroupBegin):
            args.append(read_arg(
                src, next(src), tolerance=tolerance, mode=mode))
            n_required -= 1
            continue
        elif src.hasNext() and (src.peek().category == TC.BracketBegin):
            #explictly marked optional arg
            break
        elif src.hasNext() and n_required > 0:
            next_token = next(src)
            if next_token.category == TC.Escape:
                name, _ = read_command(src, 0, 0, tolerance=tolerance, mode=mode)
                args.append(TexCmd(name, position=next_token.position))
                n_required -= 1
            else:
                # deals with the special case where the users do not write {}
                # if not args and mode == MODE_MATH:
                #     for t in list(next_token):
                #         if t != " " and n_required > 0:
                #             args.append('{%s}' % t)
                #             n_required -= 1
                # else:
                #     args.append('{%s}' % next_token)
                #     n_required -= 1
                
                for t in list(next_token):
                    if t != " " and n_required > 0:
                        args.append('{%s}' % t)
                        n_required -= 1
                
            continue

        if spacer:
            src.backward(1)
        break
    return n_required


def read_arg(src, c, tolerance=0, mode=MODE_NON_MATH):
    r"""Read the argument from buffer.

    Advances buffer until right before the end of the argument.

    :param Buffer src: a buffer of tokens
    :param str c: argument token (starting token)
    :param int tolerance: error tolerance level (only supports 0 or 1)
    :param str mode: math or not math mode
    :return: the parsed argument
    :rtype: TexGroup

    >>> from TexSoup.category import categorize
    >>> from TexSoup.tokens import tokenize
    >>> s = r'''{\item\abovedisplayskip=2pt\abovedisplayshortskip=0pt~\vspace*{-\baselineskip}}'''
    >>> buf = tokenize(categorize(s))
    >>> read_arg(buf, next(buf))
    BraceGroup(TexCmd('item'))
    >>> buf = tokenize(categorize(r'{\incomplete! [complete]'))
    >>> read_arg(buf, next(buf), tolerance=1)
    BraceGroup(TexCmd('incomplete'), '! ', '[', 'complete', ']')
    """
    content = [c]
    arg = ARG_BEGIN_TO_ENV[c.category]
    if arg.token_begin == TC.GroupBegin:
         GroupTracker.push(arg.token_begin)
    while src.hasNext():
        if src.peek().category == arg.token_end:
            if arg.token_end == TC.GroupEnd: 
                GroupTracker.pop()
            src.forward()
            return arg(*content[1:], position=c.position)
        else:
            content.append(read_expr(src, tolerance=tolerance, mode=mode, is_arg=True, arg_end=arg.token_end))

    if tolerance == 0:
        clo = CharToLineOffset(str(src))
        line, offset = clo(c.position)
        raise TypeError(
            '[Line: %d, Offset %d] Malformed argument. First and last elements '
            'must match a valid argument format. In this case, TexSoup'
            ' could not find matching punctuation for: %s.\n'
            'Just finished parsing: %s' %
            (line, offset, c, content))
    return arg(*content[1:], position=c.position)


def read_spacer(buf):
    r"""Extracts the next spacer, if there is one, before non-whitespace

    Define a spacer to be a contiguous string of only whitespace, with at most
    one line break.

    >>> from TexSoup.category import categorize
    >>> from TexSoup.tokens import tokenize
    >>> read_spacer(Buffer(tokenize(categorize('   \t    \n'))))
    '   \t    \n'
    >>> read_spacer(Buffer(tokenize(categorize('   \t    \n\t \n  \t\n'))))
    '   \t    \n\t '
    >>> read_spacer(Buffer(tokenize(categorize('{'))))
    ''
    >>> read_spacer(Buffer(tokenize(categorize('   \t    \na'))))
    ''
    >>> read_spacer(Buffer(tokenize(categorize('   \t    \n\t \n  \t\na'))))
    '   \t    \n\t '
    """
    if buf.hasNext() and buf.peek().category == TC.MergedSpacer:
        return next(buf)
    return ''


def read_command(buf, n_required_args=-1, n_optional_args=-1, skip=0,
                 tolerance=0, mode=MODE_NON_MATH):
    r"""Parses command and all arguments. Assumes escape has just been parsed.

    No whitespace is allowed between escape and command name. e.g.,
    :code:`\ textbf` is a backslash command, then text :code:`textbf`. Only
    :code:`\textbf` is the bold command.

    >>> from TexSoup.category import categorize
    >>> from TexSoup.tokens import tokenize
    >>> buf = Buffer(tokenize(categorize('\\sect  \t    \n\t{wallawalla}')))
    >>> next(buf)
    '\\'
    >>> read_command(buf)
    ('sect', [BraceGroup('wallawalla')])
    >>> buf = Buffer(tokenize(categorize('\\sect  \t   \n\t \n{bingbang}')))
    >>> _ = next(buf)
    >>> read_command(buf)
    ('sect', [])
    >>> buf = Buffer(tokenize(categorize('\\sect{ooheeeee}')))
    >>> _ = next(buf)
    >>> read_command(buf)
    ('sect', [BraceGroup('ooheeeee')])
    >>> buf = Buffer(tokenize(categorize(r'\item aaa {bbb} ccc\end{itemize}')))
    >>> read_command(buf, skip=1)
    ('item', [])
    >>> buf.peek()
    ' aaa '
    # \renewcommand{\subsection}[1]{{\textit{#1.~}}}
    # push [renewcommand, 0]  #number args read so far
    # push [subsection, 0]
    # pop [subsection, 0] --> increment parent args detected
    #    ++ -> [renewcommnand,  1]
    # push [textit, 0]

    # >>> buf = Buffer(tokenize(categorize('\\sect abcd')))
    # >>> _ = next(buf)
    # >>> read_command(buf)
    # ('sect', ('a',))
    """
    for _ in range(skip):
        next(buf)

    name = next(buf)
    #push name to ParentTracker stack
    ParentTracker.push([name, 0])

    token = Token('', buf.position)

    if n_required_args < 0 and n_optional_args < 0:
        n_required_args, n_optional_args = MacroSignatures.sig_dict.get(name, (-1, -1))
    args = read_args(
        buf,
        n_required_args, n_optional_args,
        tolerance=tolerance, mode=mode
    )
    #pop ParentTracker
    parent_name, args_found = ParentTracker.pop() 
    #increment args_found for (now) top item 
    ParentTracker.increment_top_count()
    return name, args
