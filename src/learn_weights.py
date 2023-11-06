import math
import random
import time
from pprint import pprint

from matplotlib import pyplot as plt
from mpc import mpc
import torch

from src.Action import Action
from src.GeneticAlgorithm import initialize_population, evaluate_population, select_population, mutate_population
from src.Point2D import Point2D
from src.Rocket import State, Weight, Rocket
from src.create_environment import create_env
from src.RocketDynamics import RocketDynamics
from src.create_graph import create_graph
from src.hyperparameters import TIMESTEPS, ACTION_LOW, ACTION_HIGH, LQR_ITER, N_BATCH, population_size, \
    generations_count, GRAVITY, mutation_rate
from src.mars_landing import fitness_function

# TODO move this info somewhere else:
# RL setting chosen : MDP (Markov Decision Process). #TODO revisit choices
# because
# I have access to a model (given an action, I am able to predict what next state will be),
# a reward function (able to know immediate reward, which is 0 all the time expect when actually landing) but
# I don't have access to a Value Function (no quick way to know the expected reward sum)
# and there are (finite) actions the agent is able take.
#
# then I am exploring MPC algorithm (Model Predictive Control) ... Not rdy yet.

# Model to -> Policy = Planning

# Policy-Based RL
# The world outside my agent is stationary (independent of the agent actions).


def find_landing_spot(mars_surface: list[Point2D])-> tuple[Point2D, Point2D]:
    for i in range(len(mars_surface) - 1):
        if mars_surface[i + 1].y == mars_surface[i].y:
            return mars_surface[i], mars_surface[i + 1]
    raise Exception('no landing site on test-case data')


def learn_weights(mars_surface: list[Point2D], init_rocket: Rocket, env):
    x_max = 7000
    y_max = 3000
    env: list[list[bool]] = create_env(mars_surface, x_max, y_max)
    landing_spot = find_landing_spot(mars_surface)
    initial_state = (2500, 2700, 0, 0, 550, 0, 0, env, landing_spot)
    create_graph(mars_surface, 'Landing on Mars')

    population = initialize_population(population_size, [(0, 4), (-90, 90)])  # TODO reduce rotation and thrust LATER DURING NEXT SELECTION -+15% MAX
    for generation in range(generations_count):
        fitness_scores = evaluate_population(population, fitness_function, initial_state, generation)
        print(generation)
        best_individual = population[fitness_scores.index(max(fitness_scores))]  # ELite ?
        selected_population = select_population(population, fitness_scores)
        population = mutate_population(selected_population, mutation_rate)
        population.append(best_individual)  # TODO review this selection process and elite process
