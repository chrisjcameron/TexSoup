from dataclasses import dataclass, field


NO_ARG_MATH_CMD = """
alpha approx ast beta bigcup blacksquare Box boxtimes cap cdot cdots chi 
colon complement cong cup Delta delta div downarrow emptyset epsilon 
equiv eta exists forall Gamma gamma geq Im in infty iota kappa 
Lambda lambda Leftarrow leftarrow leftharpoondown leftharpoonup 
leftrightarrow leq longmapsto mapsto mu nabla nearrow neg neq 
nexists notin nu nwarrow Omega omega oplus otimes partial perp 
Phi phi Pi pi Psi psi Re rho Rightarrow rightarrow rightharpoondown 
rightharpoonup rightleftharpoons searrow Sigma sigma simeq square star
subset subseteq surd swarrow tau Theta theta times to triangle uparrow Updownarrow 
Upsilon upsilon varepsilon varnothing varphi varrho vartheta vee 
wedge wp Xi xi zeta
""".strip().split()

SIGNATURES = {
    'addcontentsline': (3, 0),
    'address': (1, 0),
    'addtocontents': (2, 0),
    'addtocounter': (2, 0),
    'addtolength': (2, 0),
    'alph': (1, 0),
    'author': (1, 0),
    'begin': (1,0),
    'bibitem': (1, 0),
    'bibliography': (1, 0),
    'bibliographystyle': (1, 0),
    'binom': (2, 0),
    'cap': (0, 0),
    'caption': (1, 1),
    'cc': (1, 0),
    'chapter': (1, 1),
    'chapter*': (1, 0),
    'circle': (1, 0),
    'circle*': (1, 0),
    'cite': (1, 1),
    'cline': (1, 0),
    'closing': (1, 0),
    'cup': (0, 0),
    'dashbox': (2, 2),
    'date': (1, 0),
    'def': (2, 0),
    'documentstyle': (1, 1),
    'encl': (1, 0),
    'end': (1, 0),
    'fbox': (1, 0),
    'fnsymbol': (1, 0),
    'footnote': (1, 0),
    'footnotetext': (1, 0),
    'frac': (2, 0),
    'frame': (1, 0),
    'framebox': (1, 2),
    'glossary': (1, 0),
    'glossaryentry': (2, 0),
    'hspace': (1, 0),
    'hspace*': (1, 0),
    'hypenation': (1, 0),
    'in': (0, 0),
    'include': (1, 0),
    'includeonly': (1, 0),
    'index': (1, 0),
    'indexentry': (2, 0),
    'infty': (0, 0),
    'input': (1, 0),
    'item': (0, 1),
    'label': (1, 0),
    'label': (1, 0),
    'lefteqn': (1, 0),
    'line': (1, 1),
    'linebreack': (0, 1),
    'linethickness': (1, 0),
    'makebox': (1, 2),
    'marginpar': (1, 0),
    'markboth': (2, 0),
    'markright': (1, 0),
    'mbox': (1, 0),
    'multicolumn': (3, 0),
    'multiput': (2, 2),
    'newcommand': (2, 1),
    'newcommand': (2, 1),
    'newcounter': (1, 1),
    'newenvironment': (3, 1),
    'newfont': (2, 0),
    'newlength': (1, 0),
    'newsavebox': (1, 0),
    'newtheorem': (2, 2),
    'noindent': (0, 0),
    'nolinebreak': (0, 1),
    'nopagebreak': (0, 1),
    'notin': (0, 0),
    'opening': (1, 0),
    'oval': (0, 1),
    'overbrace': (1, 0),
    'overline': (1, 0),
    'pagebreak': (0, 1),
    'pagenumbering': (1, 0),
    'pageref': (1, 0),
    'pagestyle': (1, 0),
    'paragraph': (1, 1),
    'paragraph*': (1, 1),
    'parbox': (2, 1),
    'part': (1, 1),
    'part*': (1, 0),
    'pmod': (1, 0),
    'put': (1, 1),
    'raisebox': (2, 2),
    'ref': (1, 0),
    'renewcommand': (2, 1),
    'renewenvironment': (3, 1),
    'roman': (1, 0),
    'rule': (2, 1),
    'savebox': (2, 2),
    'sbox': (2, 0),
    'section': (1, 1),
    'section*': (1, 0),
    'setcounter': (2, 0),
    'setlength': (2, 0),
    'settowidth': (2, 0),
    'shortstack': (1, 1),
    'signature': (1, 0),
    'sqrt': (1, 1),
    'stackrel': (2, 0),
    'subparagraph': (1, 1),
    'subparagraph*': (1, 0),
    'subsection': (1, 1),
    'subsection*': (1, 0),
    'subsubsection': (1, 1),
    'subsubsection*': (1, 0),
    'symbol': (1, 0),
    'textbf': (1, 0),
    'thanks': (1, 0),
    'thispagestyle': (1, 0),
    'title': (1, 0),
    'twocolumn': (0, 1),
    'typein': (1, 1),
    'typeout': (1, 0),
    'underbrace': (1, 0),
    'underline': (1, 0),
    'usebox': (1, 0),
    'usecounter': (1, 0),
    'value': (1, 0),
    'vector': (1, 1),
    'vspace': (1, 0),
    'vspace*': (1, 0),
    'widehat': (1, 0),
    'widetilde': (1, 0),
}
SIGNATURES.update({cmd:(0,0) for cmd in NO_ARG_MATH_CMD})


class ParentTracker:
    stack = []

    @classmethod
    def push(cls, item):
        cls.stack.append(item)

    @classmethod
    def pop(cls):
        # if cls.stack:
        #     cur = cls.stack[0]
        #     cls.stack = cls.stack[1:]
        #     return cur
        # else:
        #     return None

        if cls.stack:
            cur = cls.stack[-1]
            cls.stack = cls.stack[:-1]
            return cur
        else:
            return None

    @classmethod
    def increment_top_count(cls):
        if cls.stack:
            cls.stack[-1][1] += 1

    # @classmethod
    # def __getitem__(cls, index):
    #     return cls.stack[index]

    # @classmethod
    # def __len__(cls):
    #     return len(cls.stack)

    @classmethod
    def reset(cls):
        cls.stack.clear()

class GroupTracker:
    stack = []

    @classmethod
    def push(cls, item):
        cls.stack.append(item)
    

    @classmethod
    def pop(cls):
        if cls.stack:
            cur = cls.stack[-1]
            cls.stack = cls.stack[:-1]
            return cur
        else:
            return None

    @classmethod
    def reset(cls):
        cls.stack.clear()

@dataclass
class CustomMacro:
   name: str 
   num_args: tuple[int, int]
   default_val: str
   def_fmt_str: str


class CustomDefs:
    macros_dict = {}

    @classmethod
    def reset(cls):
        cls.macros_dict.clear()


class MacroSignatures:
    sig_dict = SIGNATURES.copy()

    @classmethod
    def reset(cls):
        cls.sig_dict = SIGNATURES.copy()

