import os
import numpy as np
import json
import matplotlib.pyplot as plt
from plotly.offline import download_plotlyjs, init_notebook_mode, plot, iplot
import plotly.graph_objs as go

from skill import Skill
from agent import Agent, choose_agent
from task import Task
from timeline import Timeline, Event
import my_parameters as P

# Useful if you need to print JSON:
# from pprint import pprint

class Workplace:
    # ---------- INITIALISATION  ----------

    def __init__(self, file=None, verbose=False):
        # Create an empty workplace
        self.agents = []
        self.completed_tasks = []
        self.current_task = None
        self.tasks_todo = []
        self.time = 0
        self.timeline = Timeline() # list of TimePoints
        self.coordination_times = {}
        self.Tperf = {}

        self.verbose = verbose

        if file:
            print("Reading from input file " + file + "...\n")
            self.parse_json(file, verbose)


		
    def parse_json(self, filename, verbose = False):
        ''' reads json file and loads agents, tasks and parameters'''
        with open(filename) as f:
            data = json.load(f)
        for idx, agent in enumerate(data['agents'], verbose):
            self.add_agent(idx, agent, verbose = verbose)
        for idx, task in enumerate(data['tasks']):
            self.add_task(idx, task)

        self.import_parameters(data['parameters'])

    def add_agent(self, idx, agent, verbose = False):
        skills = [Skill(_id = skill['id'],
                        exp = skill['exp'],
                        mot = skill['mot'])
                  for skill in agent['skillset']]

        mbti = agent['mbti'] if 'mbti' in agent else None
        initial_frustration = agent['initial_frustration'] if 'initial_frustration' in agent else None

        self.agents.append(Agent(_id = idx, mbti = mbti,
                                 initial_frustration = initial_frustration,
                                 skillset = skills,
                                 verbose=verbose))

    def add_task(self, idx, task):
        self.tasks_todo.append(Task(_id = idx, json_task = task))

    def import_parameters(self, params):
        ''' Loads all parameters from dictionary that comes from json file'''
        if 'task_unit_duration' in params:
            P.TASK_UNIT_DURATION = params['task_unit_duration']
        if 'alpha_e' in params:
            P.ALPHA_E = params['alpha_e']
        if 'alpha_m' in params:
            P.ALPHA_M = params['alpha_m']
        if 'alpha_f' in params:
            P.ALPHA_F = params['alpha_f']
        if 'beta' in params:
            P.BETA = params['beta']
        if 'lam_learn' in params:
            P.LAM_LEARN = params['lam_learn']
        if 'lam_motiv' in params:
            P.LAM_MOTIV = params['lam_motiv']
        if 'mu_learn' in params:
            P.MU_LEARN = params['mu_learn']
        if 'mu_motiv' in params:
            P.MU_MOTIV = params['mu_motiv']
        if 'th_e' in params:
            P.TH_E = params['th_e']
        if 'th_m' in params:
            P.TH_M = params['th_m']
        if 'max_e' in params:
            P.MAX_E = params['max_e']
        if 'max_m' in params:
            P.MAX_M = params['max_m']
        if 'max_h' in params:
            P.MAX_H = params['max_h']
        if 'excite' in params:
            P.EXCITE = params['excite']
        if 'inhibit' in params:
            P.INHIBIT = params['inhibit']

        # Normalise alphas
        if P.ALPHA_E + P.ALPHA_F + P.ALPHA_M != 1:
            factor = 1 / (P.ALPHA_E + P.ALPHA_F + P.ALPHA_M)
            P.ALPHA_E *= factor
            P.ALPHA_F *= factor
            P.ALPHA_M *= factor

    # ---------- TASK PROCESSING ----------

    def process_tasks(self):
        ''' Just a while loop that processes all the tasks in another function'''
        # While there is work to do...
        while len(self.tasks_todo) > 0:
            # Tasks are handled one at a time
            self.current_task = self.tasks_todo.pop(0)

            self.process_current_task()
            
            if self.verbose:
                print('Processed task:\n' + str(self.current_task) + '\n')

            self.completed_tasks.append(self.current_task)
            self.current_task = None
        
        # Output frustration values, for later plot
        media_path = '../media/' if os.path.isdir('../media') \
                     else '../../media/'
        with open(media_path + 'moods.data', 'w') as f:
            for i in range(len(self.agents[0].frustration)):
                f.write(str(self.agents[0].frustration[i]) + ', ' + \
                        str(self.agents[0].frustration[i]) + '\n')

    def process_current_task(self):
        ''' Processes current tasks one by one. Called by process_tasks() '''

        # Repeat action assignment until all actions have been completed
        while True:
            # Assign agents to each of the actions
            actions_to_process = [choose_agent(self, action) for action in self.current_task.actions \
                                  if action.completion < action.duration]

            if len(actions_to_process) == 0:
                break

            assignments, allocation_times, skill_ids, action_ids = zip(*actions_to_process)
            self.coordination_times[self.time] = sum(allocation_times)

            t_perfs = [agent.calculate_performance_time(skill_ids, assignments, self.time)
                        for agent in self.agents]
            self.Tperf[self.time] = max(t_perfs) + self.coordination_times[self.time]

            # ~ HOUSEKEEPING ~
            for agent in self.agents:
                agent.flush_prev_act(assignments, skill_ids)            # Clear internal variables related to previous task
                agent.update_memory()                                   # Update expertise and motivation

            # Update current actions for all agents
            for i, assignment in enumerate(assignments):
                self.agents[assignment].current_action.append(
                    {
                        'task': self.current_task._id,
                        'action': action_ids[i],
                        'start_time': self.time
                    }
                )

                self.timeline.add_event(Event(start_time = self.time, \
                                                duration = 1,                       # Constant, for now
                                                task_id = self.current_task._id, \
                                                action_id = action_ids[i], \
                                                agent_id = assignment, \
                                                ))

            # ~ END HOUSEKEEPING ~

            self.time += 1

    # ---------- GETTERS ----------

    def get_sum_perf_time(self):
        return int(np.round(sum(self.Tperf.values())))

    # ---------- PRINTING ----------

    def plot_skills(self, agent):
        ''' Plots the expertise of two agents as a function of number of cycles'''
        y1 = np.round(np.array(agent.skillset[0].expertise))
        y2 = np.round(np.array(agent.skillset[1].expertise))
        x = np.round(np.array(list(range(len(y1)))))

        y1 = [y if y > 0 else 0 for y in y1]
        y2 = [y if y > 0 else 0 for y in y2]

        trace1 = go.Scatter(
            x = x,
            y = y1,
            mode = 'lines+markers',
            name = 'Skill 1'
        )

        trace2 = go.Scatter(
            x = x,
            y = y2,
            mode = 'lines+markers',
            name = 'Skill 2'
        )

        layout = go.Layout(
            title='Expertise',
            xaxis=dict(
                title='Cycles',
                titlefont=dict(
                    family='Arial, sans-serif',
                    size=24,
                    color='black'
                )
            ),
            yaxis=dict(
                title='Expertise',
                titlefont=dict(
                    family='Arial, sans-serif',
                    size=24,
                    color='black'
                )
            )
        )

        data = [trace1, trace2]

        fig = go.Figure(data=data, layout=layout)

        iplot(fig)

    def plot_skills_matplotlib(self, agent):
        ''' Plots the expertise of two agents as a function of number of cycles'''
        y1 = np.round(np.array(agent.skillset[0].expertise))
        y2 = np.round(np.array(agent.skillset[1].expertise))
        x = np.round(np.array(list(range(len(y1)))))

        y1 = [y if y > 0 else 0 for y in y1]
        y2 = [y if y > 0 else 0 for y in y2]

        fig = plt.figure()

        plt.plot(x, y1, '.-', x, y2, '.-')
        plt.xlabel('Cycles')
        plt.ylabel('Expertise')
        plt.title('Evolution of expertise: Agent ' + str(agent._id))
        plt.legend(['Skill 1', 'Skill 2'])
        plt.draw()

        return fig

    def plot_motivation(self, agent):
        ''' Plots the motivation of two agents as a function of #cycles'''
        y1 = np.round(np.array(agent.skillset[0].motivation))
        y2 = np.round(np.array(agent.skillset[1].motivation))
        x = np.round(np.array(list(range(len(y1)))))

        y1 = [y if y > 0 else 0 for y in y1]
        y2 = [y if y > 0 else 0 for y in y2]

        trace1 = go.Scatter(
            x = x,
            y = y1,
            mode = 'lines+markers',
            name = 'Skill 1'
        )

        trace2 = go.Scatter(
            x = x,
            y = y2,
            mode = 'lines+markers',
            name = 'Skill 2'
        )

        layout = go.Layout(
            title='Motivation',
            xaxis=dict(
                title='Cycles',
                titlefont=dict(
                    family='Arial, sans-serif',
                    size=24,
                    color='black'
                )
            ),
            yaxis=dict(
                title='Motivation',
                titlefont=dict(
                    family='Arial, sans-serif',
                    size=24,
                    color='black'
                )
            )
        )

        data = [trace1, trace2]

        fig = go.Figure(data=data, layout=layout)

        iplot(fig)

    def plot_frustration(self):
        ''' Plots frustration of two agents as a function of #cycles'''
        y0 = np.array(self.agents[0].frustration)
        y1 = np.array(self.agents[1].frustration)
        x = np.array(list(range(len(y1))))

        trace1 = go.Scatter(
            x = x,
            y = y0,
            mode = 'lines+markers',
            name = 'Agent 1'
        )

        trace2 = go.Scatter(
            x = x,
            y = y1,
            mode = 'lines+markers',
            name = 'Agent 2'
        )

        layout = go.Layout(
            title='Frustration',
            xaxis=dict(
                title='Cycles',
                titlefont=dict(
                    family='Arial, sans-serif',
                    size=24,
                    color='black'
                )
            ),
            yaxis=dict(
                title='Frustration',
                titlefont=dict(
                    family='Arial, sans-serif',
                    size=24,
                    color='black'
                )
            ),
            showlegend=True
        )

        data = [trace1, trace2]

        fig = go.Figure(data=data, layout=layout)

        iplot(fig)
    
    def plot_frustration_matplotlib(self):
        ''' Plots frustration of two agents as a function of #cycles'''
        y0 = np.array(self.agents[0].frustration)
        y1 = np.array(self.agents[1].frustration)
        x = np.array(list(range(len(y1))))

        fig = plt.figure()

        plt.plot(x, y0, '.-', x, y1, '.-')
        plt.xlabel('Cycles')
        plt.ylabel('Frustration')
        plt.title('Frustration')
        plt.legend(['Agent 1', 'Agent 2'])
        plt.draw()

        return fig

    def plot_allocations(self):
        ''' Plots allocation time it took for every cycle'''
        y0 = np.array(self.agents[0].allocation_times)
        y1 = np.array(self.agents[1].allocation_times)
        x = np.array(list(range(len(y1))))

        # y1 = [y if y > 0 else 0 for y in y1]
        # y2 = [y if y > 0 else 0 for y in y2]

        trace1 = go.Scatter(
            x = x,
            y = y0,
            mode = 'lines+markers',
            name = 'Agent 1'
        )

        trace2 = go.Scatter(
            x = x,
            y = y1,
            mode = 'lines+markers',
            name = 'Agent 2'
        )

        layout = go.Layout(
            title='Allocations',
            xaxis=dict(
                title='Cycles',
                titlefont=dict(
                    family='Arial, sans-serif',
                    size=24,
                    color='black'
                )
            ),
            yaxis=dict(
                title='Allocation time',
                titlefont=dict(
                    family='Arial, sans-serif',
                    size=24,
                    color='black'
                )
            )
        )

        data = [trace1, trace2]

        fig = go.Figure(data=data, layout=layout)

        iplot(fig)

    def plot_performance(self):
        ''' Plots performance times of the agents and of the whole system'''
        y = []
        y.append(np.round(np.array(list(self.Tperf.values()))))
        y.append(np.round(np.array(list(self.coordination_times.values()))))
        y.append(np.round(np.array(list(self.agents[0].performance_times.values()))))
        y.append(np.round(np.array(list(self.agents[1].performance_times.values()))))

        for _y in y:
            _y = [y if y > 0 else 0 for y in _y]

        x = np.array(list(range(len(y[0]))))

        names = [
            'System',
            'Coordination Time',
            'Agent 1',
            'Agent 2'
        ]

        data = [
                go.Scatter(
                    x = x,
                    y = _y,
                    mode = 'lines+markers',
                    name = names[i]
                ) for i, _y in enumerate(y)
               ]

        layout = go.Layout(
            title='Performance',
            xaxis=dict(
                title='Cycles',
                titlefont=dict(
                    family='Arial, sans-serif',
                    size=24,
                    color='black'
                )
            ),
            yaxis=dict(
                title='Performance Time',
                titlefont=dict(
                    family='Arial, sans-serif',
                    size=24,
                    color='black'
                )
            )
        )

        fig = go.Figure(data=data, layout=layout)
        iplot(fig)

    def plot_performance_matplotlib(self):
        ''' Plots performance times of the agents and of the whole system'''
        y = []
        y.append(np.round(np.array(list(self.Tperf.values()))))
        y.append(np.round(np.array(list(self.coordination_times.values()))))
        y.append(np.round(np.array(list(self.agents[0].performance_times.values()))))
        y.append(np.round(np.array(list(self.agents[1].performance_times.values()))))

        for _y in y:
            _y = [y if y > 0 else 0 for y in _y]

        x = np.array(list(range(len(y[0]))))

        fig = plt.figure()

        plt.plot(x, y[0], '.-', x, y[1], '.-', x, y[2], '.-', x, y[3], '.-')
        plt.xlabel('Cycles')
        plt.ylabel('Time')
        plt.title('Performance')
        plt.legend(['System', 'Coordination Time', 'Agent 1', 'Agent 2'])
        plt.draw()

        return fig        

    def print_parameters(self):
        print('task_unit_duration: ' + str(P.TASK_UNIT_DURATION))
        print('alpha_e: ' + str(P.ALPHA_E))
        print('alpha_m: ' + str(P.ALPHA_M))
        print('alpha_f: ' + str(P.ALPHA_F))
        print('beta: ' + str(P.BETA))
        print('lam_learn: ' + str(P.LAM_LEARN))
        print('lam_motiv: ' + str(P.LAM_MOTIV))
        print('mu_learn: ' + str(P.MU_LEARN))
        print('mu_motiv: ' + str(P.MU_MOTIV))
        print('th_e: ' + str(P.TH_E))
        print('th_m: ' + str(P.TH_M))
        print('max_e: ' + str(P.MAX_E))
        print('max_m: ' + str(P.MAX_M))
        print('max_h: ' + str(P.MAX_H))
        print('excite: ' + str(P.EXCITE))
        print('inhibit: ' + str(P.INHIBIT))

        print('\n')

        print('Maximum number of steps in coordination:' + str(P.MAX_COORD_STEPS))

        print('\n')

        mbti_types = ['ESTJ', 'ESTP', 'ESFJ', 'ESFP', 'ENTJ', 'ENTP', 'ENFJ', 'ENFP', 'ISTJ', 'ISTP', 'ISFJ', 'ISFP', 'INTJ', 'INTP', 'INFJ', 'INFP']

        print('MBTI Matrix:')
        print('\t'.join(mbti_types))
        for i in range(len(mbti_types)):
            print(mbti_types[i] + '\t')
            for j in range(len(mbti_types)):
                print(P.MBTI[i][j], end='\t')

    def print_history(self):
        ''' Debugging information: same as Gantt diagram'''
        for i in range(len(self.timeline)):
            print('--- Time Point ' + str(i) + ' ---')
            print(self.timeline.events[i])

    def agents_string(self):
        return 'Agents:\n' + '\n'.join(list(map(str, self.agents)))

    def tasks_string(self):
        return 'TASKS:\n\n' + '\n'.join(list(map(str, self.tasks_todo)))

    def print_current_state(self):
        ''' Printing for Debugging purposes '''
        # Print time stamp
        print("Time elapsed:")
        print(self.time, end='')
        print(" time units.\n")

        # Print Tasks: Completed, Current, To-Do
        print("Completed tasks:")
        for task in self.completed_tasks:
            print(task)

        print("Current task:")
        print(self.current_task)

        print("Future tasks:")
        for task in self.tasks_todo:
            print(task)

        # Print Agents: List, Current Engagement...
        print("Currently employed agents:")
        for agent in self.agents:
            print(agent)

        # Print history of completed actions
        print("History:")
        self.timeline.plot_gantt()
