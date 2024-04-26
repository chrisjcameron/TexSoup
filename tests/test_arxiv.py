
import sys
import os
sys.path.insert(0, os.path.abspath("../TexSoup"))
print(sys.path)
import TexSoup as TS
print(TS.__path__)


min_example=r"""
\renewcommand{\subsection}[1]{{\textit{#1.~}}}
""".strip().replace('\\}\\', '\\} \\').replace(')}', ') }')
print(TS.TexSoup(min_example, tolerance=0))

min_example=r"""
\begin{equation*}
        \frac{\partial u}{\partial t} = -\nabla \cdot (vu),
        \label{eqn:gov_eqn}
\end{equation*}
""".strip().replace('\\}\\', '\\} \\').replace(')}', ') }')
print(TS.TexSoup(min_example, tolerance=0))


from TexSoup.category import categorize
from TexSoup.tokens import tokenize
from TexSoup.reader import read_args
test = lambda s, *a, **k: read_args(tokenize(categorize(s)), *a, **k)
print(test('[walla]{walla}{ba]ng}').all)  # 'regular' arg parse
    #[BracketGroup('walla'), BraceGroup('walla'), BraceGroup('ba', ']', 'ng')]
print(test('\t[wa]\n{lla}\n\n{b[ing}').all)  # interspersed spacers + 2 newlines
    #[BracketGroup('wa'), BraceGroup('lla')]
print(test('\t[\t{a]}bs', 2, 0).all)  # use char as arg, since no opt args)
    #[BraceGroup('['), BraceGroup('a', ']')]
print(test('\n[hue]\t[\t{a]}', 2, 1).all)  # check stop opt arg capture)
    #[BracketGroup('hue'), BraceGroup('['), BraceGroup('a', ']')]
print(test('\t\\item').all)
    #[]
print(test('   \t    \n\t \n{bingbang}').all)
    #[]
print(test('[tempt]{ing}[WITCH]{doctorrrr}', 0, 0).all)
    #[]


min_example=r"""
\begin{tikzpicture}[->,>=stealth',shorten >=1pt,auto,node distance=2.5cm,%3cm
                    thick,main node/.style={circle,draw,font=\sffamily\bfseries}]
                    \centering

  \node[main node] (1) {$u_{i-1}$};
  \node[main node] (2) [right of=1] {$u_{i}$};
  \node[main node] (3) [right of=2] {$u_{i+1}$};

  \path[every node/.style={font=\sffamily\small}]
    (1) edge node[above] {$v/\Delta{x}$} (2)
    (2) edge node [above] {$v/\Delta{x}$} (3);
    \path (0,-1cm);
\end{tikzpicture}}
""".strip().replace('\\}\\', '\\} \\').replace(')}', ') }')
print(TS.TexSoup(min_example, tolerance=0))


min_example=r"""
\begin{figure}[H]
\centering
\subfigure[first order upwind scheme]{\label{fig:graph_upwind}
\begin{tikzpicture}[->,>=stealth',shorten >=1pt,auto,node distance=2.5cm,%3cm
                    thick,main node/.style={circle,draw,font=\sffamily\bfseries}]
                    \centering

  \node[main node] (1) {$u_{i-1}$};
  \node[main node] (2) [right of=1] {$u_{i}$};
  \node[main node] (3) [right of=2] {$u_{i+1}$};

  \path[every node/.style={font=\sffamily\small}]
    (1) edge node[above] {$v/\Delta{x}$} (2)
    (2) edge node [above] {$v/\Delta{x}$} (3);
    \path (0,-1cm);
\end{tikzpicture}}
\subfigure[second order central scheme]{\label{fig:graph_central}
\begin{tikzpicture}[->,>=stealth',shorten >=1pt,auto,node distance=2.5cm,
                    thick,main node/.style={circle,draw,font=\sffamily\bfseries}]
\hspace{0.5cm}
 %  \centering %\Large%
  \node[main node] (1) {$u_{i-1}$};
  \node[main node] (2) [right of=1] {$u_{i}$};
  \node[main node] (3) [right of=2] {$u_{i+1}$};

  \path[every node/.style={font=\sffamily\small}]
    (1) edge node[above] {$v/2\Delta{x}$} (2)
    (3) edge node [above] {$-v/2\Delta{x}$} (2) 
    (2) edge [bend left] node[below] {$-v/2\Delta{x}$} (1)
    (2) edge [bend right] node[below] {$v/2\Delta{x}$} (3);
\end{tikzpicture}}
\caption{Balanced graphs on which $L_{adv}$ corresponds to finite difference stencils of linear advection.}
\end{figure}
""".strip().replace('\\}\\', '\\} \\').replace(')}', ') }')
print(TS.TexSoup(min_example, tolerance=0))


