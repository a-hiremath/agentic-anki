# Calculus 1C: Integration

## The Definite Integral

The definite integral of a continuous function $f$ on $[a, b]$ is defined as:

$$
\int_a^b f(x) \, dx = \lim_{n \to \infty} \sum_{i=1}^{n} f(x_i^*) \Delta x
$$

where $\Delta x = \frac{b-a}{n}$ and $x_i^*$ is a sample point in the $i$-th subinterval.

## The Fundamental Theorem of Calculus

**Part 1**: If $f$ is continuous on $[a, b]$ and $g(x) = \int_a^x f(t) \, dt$, then $g$ is differentiable and:
$$g'(x) = f(x)$$

**Part 2**: If $F$ is any antiderivative of $f$ on $[a, b]$, then:
$$\int_a^b f(x) \, dx = F(b) - F(a)$$

This theorem establishes the connection between differentiation and integration.

## Integration Techniques

### Substitution

The substitution rule states: if $u = g(x)$, then

$$
\int f(g(x)) g'(x) \, dx = \int f(u) \, du
$$

**Key insight**: Choose $u$ to simplify the integrand. The derivative $g'(x)$ must appear as a factor.

### Integration by Parts

$$
\int u \, dv = uv - \int v \, du
$$

Use the **LIATE** rule to choose $u$: Logarithm, Inverse trig, Algebraic, Trigonometric, Exponential.

## Improper Integrals

An improper integral has an infinite limit or an unbounded integrand.

$$
\int_1^\infty \frac{1}{x^p} \, dx = \begin{cases} \frac{1}{p-1} & \text{if } p > 1 \\ \text{diverges} & \text{if } p \le 1 \end{cases}
$$

**Exception**: The integral $\int_0^1 \frac{1}{x} \, dx$ diverges even though the interval is bounded.
