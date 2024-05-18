import functools
import os
import jax
from jax import numpy as jnp
from jax import config
from dataclasses import dataclass
import tyro
from tqdm import tqdm
from matplotlib import pyplot as plt
from time import time

import mbd

dim = 800
fn_name = "Rastrigin"  # Ackley Rastrigin
a, b, c = 20, 0.2, 2 * jnp.pi
if fn_name == "Ackley":
    x_min, x_max = -5.0, 10.0
else:
    x_min, x_max = -5.0, 5.0

Nexp = 6
Nsample = 64
Ndiffuse = 100
temp_sample = 1.0
betas = jnp.linspace(1e-4, 1e-2, Ndiffuse)
alphas = 1.0 - betas
alphas_bar = jnp.cumprod(alphas)
sigmas = jnp.sqrt(1 - alphas_bar)


def ackley(Y):
    X = x_min + (x_max - x_min) * (Y + 1.0) / 2.0  # map to [-5, 10]
    part1 = -a * jnp.exp(-b / jnp.sqrt(dim) * jnp.linalg.norm(X, axis=-1))
    part2 = -(jnp.exp(jnp.mean(jnp.cos(c * X), axis=-1)))
    return part1 + part2 + a + jnp.e


def rastrigin(X):
    X = x_min + (x_max - x_min) * (X + 1.0) / 2.0  # map to [-5, 10]
    return 10.0 * dim + jnp.sum(X**2 - 10.0 * jnp.cos(2.0 * jnp.pi * X), axis=-1)


def levy(X):
    X = x_min + (x_max - x_min) * (X + 1.0) / 2.0  # map to [-5, 10]
    w = 1.0 + (X - 1.0) / 4.0
    part1 = jnp.sin(jnp.pi * w[..., 0]) ** 2
    part2 = jnp.sum(
        (w[..., :-1] - 1.0) ** 2
        * (1.0 + 10.0 * jnp.sin(jnp.pi * w[..., :-1] + 1.0) ** 2),
        axis=-1,
    )
    part3 = (w[..., -1] - 1.0) ** 2 * (1.0 + jnp.sin(2.0 * jnp.pi * w[..., -1]) ** 2)
    return part1 + part2 + part3


eval_fn = {
    "Ackley": ackley,
    "Rastrigin": rastrigin,
    "Levy": levy,
}[fn_name]


@jax.jit
def reverse_once(carry, unused):
    t, rng, mu_0t = carry

    # sample from q_i
    rng, Y0s_rng = jax.random.split(rng)
    eps_u = jax.random.normal(Y0s_rng, (Nsample, dim))
    Y0s = eps_u * sigmas[t] + mu_0t
    Y0s = jnp.clip(Y0s, -1.0, 1.0)

    # esitimate mu_0tm1
    Js = -jax.vmap(eval_fn)(Y0s)
    logp0 = (Js - Js.mean()) / Js.std() / temp_sample
    weights = jax.nn.softmax(logp0)
    mu_0tm1 = jnp.einsum("n,ni->i", weights, Y0s)  # NOTE: update only with reward

    return (t - 1, rng, mu_0tm1), Js.max()


def run_exp(seed=0):
    rng = jax.random.PRNGKey(seed)
    mu_0t = jnp.zeros([Nsample, dim]) + 1.0 * jax.random.normal(rng, (Nsample, dim))
    _, _ = reverse_once((0, rng, mu_0t), None)  # to compile
    xs, ys = [], []
    with tqdm(range(Ndiffuse - 1, 0, -1), desc="Diffusing") as pbar:
        for t in pbar:
            carry_once = (t, rng, mu_0t)
            (t, rng, mu_0t), J = reverse_once(carry_once, None)
            xs.append((Ndiffuse - 1 - t) * Nsample)
            ys.append(J)
            pbar.set_postfix({"rew": f"{J:.2e}"})
    return jnp.array(xs), jnp.array(ys)


if __name__ == "__main__":
    yss = []
    for seed in range(Nexp):
        xs, ys = run_exp(seed)
        yss.append(ys)
    ys = jnp.stack(yss).mean(axis=0)
    jnp.save(
        f"{mbd.__path__[0]}/../results/bbo/{fn_name}-{dim}d_MBD.npy",
        jnp.array([xs, ys]),
    )
