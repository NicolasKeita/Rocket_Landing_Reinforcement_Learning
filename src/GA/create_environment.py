import math
import random

import gymnasium
import numpy as np
from gymnasium import spaces
from matplotlib import pyplot as plt
from shapely import LineString, Point, MultiPoint

from src.GA.graph_handler import create_graph, display_graph, plot_terminal_state_rewards
from src.TD3_SB3.math_utils import distance_to_line, distance, distance_2


class RocketLandingEnv(gymnasium.Env):
    def __init__(self):
        initial_pos = [2500, 2500]
        self.rewards_episode = []
        self.prev_shaping = None
        self.reward_plot = []
        self.trajectory_plot = []
        surface_points, np_surface_points = self.parse_planet_surface()
        self.landing_spot = self.find_landing_spot(surface_points)

        path_to_the_landing_spot = self.search_path(initial_pos, np_surface_points, self.landing_spot, [])
        self.surface = LineString(surface_points.geoms)
        self.initial_fuel = 550
        self.initial_state = np.array([
            initial_pos[0],  # x
            initial_pos[1],  # y
            0,  # horizontal speed
            0,  # vertical speed
            self.initial_fuel,  # fuel remaining
            0,  # rotation
            0,  # thrust power
            distance_to_line(initial_pos, self.landing_spot),  # distance to landing spot
            distance_to_line(initial_pos, self.surface)  # distance to surface
        ])
        self.state_intervals = [
            [0, 7000],  # x
            [0, 3000],  # y
            [-150, 150],  # vs
            [-150, 150],  # hs
            [0, self.initial_fuel],  # fuel remaining
            [-90, 90],  # rot
            [0, 4],  # thrust
            [0, 3000],  # distance squared landing_spot
            [0, 3000]  # distance squared surface
        ]
        self.state = self.initial_state
        self.action_constraints = [15, 1]
        self.gravity = 3.711

        self.observation_space = spaces.Box(low=np.array([0.0] * 9), high=np.array([1.0] * 9))

        action_1_bounds = [-1, 1]
        action_2_bounds = [-1, 1]
        action_space_dimension = 2

        self.action_space = spaces.Box(
            low=np.array([action_1_bounds[0], action_2_bounds[0]]),
            high=np.array([action_1_bounds[1], action_2_bounds[1]]),
            shape=(action_space_dimension,)
        )
        fig, (ax_terminal_state_rewards, ax_trajectories) = plt.subplots(2, 1, figsize=(10, 8))
        self.fig = fig
        # plt.close(fig)
        # self.ax_rewards = ax_mean_rewards
        self.ax_trajectories = ax_trajectories
        self.ax_terminal_state_rewards = ax_terminal_state_rewards
        create_graph(self.surface, 'Landing on Mars', ax_trajectories, path_to_the_landing_spot)

    @staticmethod
    def parse_planet_surface():
        input_file = '''
            6
            0 100
            1000 500
            1500 100
            3000 100
            5000 1500
            6999 1000
        '''
        points_coordinates = np.fromstring(input_file, sep='\n', dtype=int)[1:].reshape(-1, 2)
        return MultiPoint(points_coordinates), points_coordinates

    @staticmethod
    def find_landing_spot(planet_surface: MultiPoint) -> LineString:
        points: list[Point] = planet_surface.geoms

        for i in range(len(points) - 1):
            if points[i].y == points[i + 1].y:
                return LineString([points[i], points[i + 1]])
        raise Exception('no landing site on test-case data')

    def normalize_state(self, raw_state: list):
        return np.array([(val - interval[0]) / (interval[1] - interval[0])
                         for val, interval in zip(raw_state, self.state_intervals)])

    def denormalize_state(self, normalized_state: list):
        return np.array([val * (interval[1] - interval[0]) + interval[0]
                         for val, interval in zip(normalized_state, self.state_intervals)])

    def _get_obs(self):
        return self.state

    def reset(self, seed=None, options=None):
        self.prev_shaping = None
        self.state = self.normalize_state(self.initial_state)
        return self._get_obs(), {}

    def step(self, action_to_do_input):
        action_to_do = np.copy(action_to_do_input)
        action_to_do[0] = action_to_do[0] * 90
        action_to_do[1] = (action_to_do[1] + 1) / 2 * 4

        action_to_do = np.round(action_to_do)

        # print("Step done with action :", action_to_do_input, action_to_do)

        tmp = self.denormalize_state(self.state)
        self.state = self.compute_next_state(tmp, action_to_do)
        self.state = self.normalize_state(self.state)
        obs = self._get_obs()
        reward, terminated = self.reward_function_2(obs)
        self.trajectory_plot.append(self.denormalize_state(obs))
        self.rewards_episode.append(reward)
        if terminated:
            self.reward_plot.append(np.sum(self.rewards_episode))
            plot_terminal_state_rewards(self.reward_plot, self.ax_terminal_state_rewards)
            display_graph(self.trajectory_plot, 0, self.ax_trajectories)
            self.trajectory_plot = []
            self.rewards_episode = []

        return self._get_obs(), reward, terminated, False, {}

    def compute_next_state(self, state, action: list):
        x, y, hs, vs, remaining_fuel, rotation, thrust, dist_landing_spot_squared, dist_surface = state
        rot, thrust = limit_actions(rotation, thrust, action)
        radians = rot * (math.pi / 180)
        x_acceleration = math.sin(radians) * thrust
        y_acceleration = (math.cos(radians) * thrust) - self.gravity
        new_horizontal_speed = hs - x_acceleration
        new_vertical_speed = vs + y_acceleration
        new_x = x + hs - 0.5 * x_acceleration
        new_y = y + vs + 0.5 * y_acceleration
        new_pos: Point | list = [np.clip(new_x, 0, 7000), np.clip(new_y, 0, 3000)]

        line1 = LineString(self.surface)
        line2 = LineString([[x, y], new_pos])
        intersection: Point = line1.intersection(line2)
        if not intersection.is_empty and isinstance(intersection, Point):
            new_pos = np.array(intersection.xy).flatten()
        remaining_fuel = max(remaining_fuel - thrust, 0)

        new_state = [new_pos[0],
                     new_pos[1],
                     new_horizontal_speed,
                     new_vertical_speed, remaining_fuel, rot,
                     thrust,
                     distance_to_line(np.array(new_pos), self.landing_spot),
                     distance_to_line(new_pos, self.surface)]
        return np.array(new_state)

    def render(self):
        pass

    def close(self):
        pass

    def reward_function_2(self, state):
        middle_point = self.landing_spot.interpolate(0.5)
        x_interval = [0, 7000]
        y_interval = [0, 3000]
        scaled_x = (middle_point.x - x_interval[0]) / (x_interval[1] - x_interval[0])
        scaled_y = (middle_point.y - y_interval[0]) / (y_interval[1] - y_interval[0])
        scaled_middle_point_coordinates = (scaled_x, scaled_y)

        # dist_landing_spot_2 = distance([x, y], scaled_middle_point_coordinates)
        x, y, hs, vs, remaining_fuel, rotation, thrust, dist_landing_spot, dist_surface = state
        reward = 0
        shaping = (
                -100 * distance_2([x, y], scaled_middle_point_coordinates)
                - 100 * np.sqrt((hs-0.5 - 0) ** 2 + (vs-0.5 - 0) ** 2)
                - 100 * abs(rotation - 0.5)
        )
        # t = distance_2([x, y], scaled_middle_point_coordinates)
        if self.prev_shaping is not None:
            reward = shaping - self.prev_shaping
        self.prev_shaping = shaping

        reward -= (
            thrust * 0.30
        )

        state = self.denormalize_state(state)
        x, y, hs, vs, remaining_fuel, rotation, thrust, dist_landing_spot, dist_surface = state
        # print(t, [x,y], dist_landing_spot)
        terminated = False
        is_successful_landing = (dist_landing_spot < 1 and rotation == 0 and
                                 abs(vs) <= 40 and abs(hs) <= 20)
        is_crashed_anywhere = (y <= 1 or y >= 3000 - 1 or x <= 1 or x >= 7000 - 1 or
                               dist_surface < 1 or remaining_fuel < -4)
        is_crashed_on_landing_spot = dist_landing_spot < 1
        if is_successful_landing:
            print("SUCCESSFUL LANDING !", state)
            terminated = True
            reward = +100
            # exit(0)
        elif is_crashed_on_landing_spot:
            formatted_list = [f"{label}: {round(value):04d}" for label, value in
                              zip(['vs', 'hs', 'rotation'], [vs, hs, rotation])]
            print('Crash on landing side', formatted_list)
            terminated = True
            reward = -100
        elif is_crashed_anywhere:
            print("crash anywhere", [x, y])
            terminated = True
            reward = -100

        return reward, terminated

    def generate_random_action(self, old_rota: int, old_power_thrust: int) -> list[int]:
        action_min_max = actions_min_max([old_rota, old_power_thrust])
        action_min_max = [[int(num) for num in sublist] for sublist in action_min_max]

        random_action = [
            random.randint(action_min_max[0][0], action_min_max[0][1]),
            random.randint(action_min_max[1][0], action_min_max[1][1])
        ]
        return random_action

    def search_path(self, initial_pos, np_surface_points, landing_spot, my_path):
        # landing_spot = np.array(landing_spot.xy)
        segments = [(np_surface_points[i], np_surface_points[i + 1]) for i in range(len(np_surface_points) - 1)]

        def split_segment(segment, num_intermediate_points):
            start_point = np.array(segment[0])
            end_point = np.array(segment[1])

            intermediate_points = np.linspace(start_point, end_point, num_intermediate_points + 1)
            return intermediate_points

        def do_segments_intersect(segment1, segment2):
            x1, y1 = segment1[0]
            x2, y2 = segment1[1]
            x3, y3 = segment2[0]
            x4, y4 = segment2[1]

            # Check if segments have the same origin
            if (x1, y1) == (x3, y3) or (x1, y1) == (x4, y4) or (x2, y2) == (x3, y3) or (x2, y2) == (x4, y4):
                return False

            # Check if the segments intersect using a basic algorithm
            def orientation(p, q, r):
                val = (q[1] - p[1]) * (r[0] - q[0]) - (q[0] - p[0]) * (r[1] - q[1])
                if val == 0:
                    return 0
                return 1 if val > 0 else 2

            def on_segment(p, q, r):
                return (q[0] <= max(p[0], r[0]) and q[0] >= min(p[0], r[0]) and
                        q[1] <= max(p[1], r[1]) and q[1] >= min(p[1], r[1]))

            o1 = orientation((x1, y1), (x2, y2), (x3, y3))
            o2 = orientation((x1, y1), (x2, y2), (x4, y4))
            o3 = orientation((x3, y3), (x4, y4), (x1, y1))
            o4 = orientation((x3, y3), (x4, y4), (x2, y2))

            if (o1 != o2 and o3 != o4) or (o1 == 0 and on_segment((x1, y1), (x3, y3), (x2, y2))) or (
                    o2 == 0 and on_segment((x1, y1), (x4, y4), (x2, y2))) or (
                    o3 == 0 and on_segment((x3, y3), (x1, y1), (x4, y4))) or (
                    o4 == 0 and on_segment((x3, y3), (x2, y2), (x4, y4))):
                if not on_segment((x1, y1), (x2, y2), (x3, y3)) and not on_segment((x1, y1), (x2, y2), (x4, y4)):
                    return True

            return False

        # Example usage:
        goal = [2500, 100]
        path = []
        for segment in segments:
            segment1 = [initial_pos, goal]
            segment2 = segment
            if do_segments_intersect(segment1, segment2):
                if segment2[0][1] > segment2[1][1]:
                    path.append(segment2[0])
                elif segment2[0][1] < segment2[1][1]:
                    path.append(segment2[1])
                else:
                    path.append(random.choice([segment2[0], segment2[1]]))
                break
        if len(path) == 0:
            t = np.linspace(initial_pos, goal, 5)
            if len(my_path) == 0:
                return t
            else:
                my_path = my_path[:-1, :]
                return np.concatenate((my_path, t))
        else:
            path[0][1] = path[0][1]
            t = np.linspace(initial_pos, path[0], 5)
            return self.search_path(path[0], np_surface_points, landing_spot, t)


def action_2_min_max(old_rota: int) -> list:
    return [max(old_rota - 15, -90), min(old_rota + 15, 90)]


def action_1_min_max(old_power_thrust: int) -> list:
    return [max(old_power_thrust - 1, 0), min(old_power_thrust + 1, 4)]


def actions_min_max(action: list) -> tuple[list, list]:
    return action_2_min_max(action[0]), action_1_min_max(action[1])


def limit_actions(old_rota: int, old_power_thrust: int, action: list) -> list:
    range_rotation = action_2_min_max(old_rota)
    rot = action[0] if range_rotation[0] <= action[0] <= range_rotation[1] else min(
        max(action[0], range_rotation[0]), range_rotation[1])
    range_thrust = action_1_min_max(old_power_thrust)
    thrust = action[1] if range_thrust[0] <= action[1] <= range_thrust[1] else min(
        max(action[1], range_thrust[0]), range_thrust[1])
    return [rot, thrust]

