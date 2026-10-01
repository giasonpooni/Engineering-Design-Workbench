# Representation preservation: a mathematical review note

**Question:** Which queries and interventions remain well-defined after a
representation forgets distinctions? This note extracts one problem from NET
for mathematical review. The example is synthetic, finite and deterministic;
its declared probabilities are not empirical measurements.

## Objects and obligations

Let $S$ be a modeled state set, $r:S\to A$ a representation, $\mathcal Q$
a family of queries $q:S\to Y_q$, and $\mathcal N$ a family of interventions
$N:S\to S$. Work on the image $r(S)$; all maps here are total on their stated
domains. Define

$$
s\sim_r s'\iff r(s)=r(s'),\qquad
s\sim_{\mathcal Q}s'\iff q(s)=q(s')\text{ for all }q\in\mathcal Q.
$$

**Query preservation.** A function $\bar q:r(S)\to Y_q$ with
$q=\bar q\circ r$ exists exactly when $q$ is constant on every fibre of $r$.
Thus preserving all queries requires $\sim_r\;\subseteq\;\sim_{\mathcal Q}$.
The representation identifies exactly the query-equivalence classes only if
these relations are equal; query preservation alone does not require equality.

**Intervention preservation.** A function $\bar N:r(S)\to r(S)$ with

$$
r\circ N=\bar N\circ r
$$

exists exactly when
$r(s)=r(s')\Rightarrow r(N(s))=r(N(s'))$. The equivalence relation must
therefore be stable under every intervention the task needs. To see both
criteria, define $\bar q(r(s))=q(s)$ or $\bar N(r(s))=r(N(s))$; this is
well-defined precisely when the respective fibre condition holds. This is a
set-level factorization argument, not a new theorem or an identification of
physical objects from data.

**Observable-preserving composition.** For $T:A\to B$, $U:B\to C$ and
compatible observables $F_A,F_B,F_C$, the equations
$F_B\circ T=F_A$ and $F_C\circ U=F_B$ imply
$F_C\circ U\circ T=F_A$. Preconditions and admissible domains must match.
Approximate maps need separate error and uncertainty composition rules.

## The implemented negative fixture

Use $S=\{\text{cold-a},\text{cold-b},\text{warm-a},\text{warm-b}\}$,
$A=\{\text{cold},\text{warm}\}$ and uniform probability $\mu(s)=1/4$.
$r$ drops the `-a` / `-b` distinction and $\bar N$ is the identity on $A$:

| $s$ | $r(s)$ | $N(s)$ | $r(N(s))$ | $\bar N(r(s))$ |
| --- | --- | --- | --- | --- |
| `cold-a` | `cold` | `warm-a` | `warm` | `cold` |
| `cold-b` | `cold` | `cold-b` | `cold` | `cold` |
| `warm-a` | `warm` | `cold-a` | `cold` | `warm` |
| `warm-b` | `warm` | `warm-b` | `warm` | `warm` |

For a finite map $f$, write
$f_\#\mu(a)=\sum_{s:f(s)=a}\mu(s)$. Then

$$
(r\circ N)_\#\mu=(\bar N\circ r)_\#\mu,
\qquad P(\text{cold})=P(\text{warm})=1/2,
$$

but $r\circ N\ne\bar N\circ r$. Both source fibres have conflicting
destinations, so changing $\bar N$ cannot repair the factorization. Agreement
of these distributions loses the correspondence to each original state.

The same fixture has a temperature-proxy query with values
$270,274,290,294$ in the table's order and declared unit K. It does not factor
through $r$. Conditional means $272,292$ preserve the overall expectation
$282$ but leave mean within-fibre variance $4\,\mathrm{K}^2$ unresolved.
Preserving an expectation is different from recovering the original query.

The compatible companion fixture swaps every cold state with its matching warm
state and swaps the two coarse labels. Its intervention square commutes even
though the temperature-proxy query still loses fine-state distinctions.

## Executable source and scope

The source is draft/unmerged [PR #97](https://github.com/giasonpooni/Notations-Systems-Terminal/pull/97),
at commit `d43a420a22af51231097dfbfed6d8d73595aeb5f`:

- [Fixture and exact evaluator](https://github.com/giasonpooni/Notations-Systems-Terminal/blob/d43a420a22af51231097dfbfed6d8d73595aeb5f/src/ciw/finite_preservation.py)
- [Regression checks and exhaustive four-state map cases](https://github.com/giasonpooni/Notations-Systems-Terminal/blob/d43a420a22af51231097dfbfed6d8d73595aeb5f/tests/test_finite_preservation.py)
- [Finite preservation guide](https://github.com/giasonpooni/Notations-Systems-Terminal/blob/d43a420a22af51231097dfbfed6d8d73595aeb5f/docs/FINITE_REPRESENTATION_PRESERVATION.md)

In a checkout containing that increment, with the package installed, choose a
fresh output directory and run:

```sh
python -m ciw.net morphism finite-demo --output-dir results/finite-review
python -m ciw.net morphism finite-verify results/finite-review/registry.json results/finite-review/compatible-witness.json
python -m ciw.net morphism finite-verify results/finite-review/registry.json results/finite-review/incompatible-witness.json
```

The compatible verification returns `PASS` and exit code 0; the incompatible
one returns `FAIL` and exit code 2 with the counterexample retained. These
commands belong to the linked development increment, not the documentation
branch or current `main`. The checker covers all declared states, including
zero-probability states; conditional laws on zero-mass fibres remain undefined.
A witness establishes neither general continuous preservation nor execution
or state-admission authority.

## Questions for review

1. How should a scientific task specify enough queries and interventions to
   select an appropriate quotient, without requiring every original detail?
2. Which added structure is necessary when interventions are partial,
   stochastic, continuous or scale-dependent, and what must the induced maps
   preserve in that structure?
3. What assumptions and bounds would justify a continuous or infinite-system
   claim from finite/discretized checks?

The finite obstruction is already explicit. The open project problem is the
choice and extension of the preservation contract. A useful mathematical
answer can become an additional contract, verifier or counterexample within
the existing substrate. Evidence, operation specifications, executions,
verification occurrences and admission decisions remain separate records.
