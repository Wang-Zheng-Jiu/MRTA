import pickle
import math
import sys
import os
from itertools import product
from copy import deepcopy
import random

cur_dir = os.path.dirname(os.path.realpath(__file__))
sys.path.append(os.path.abspath(cur_dir + "/.."))
sys.path.append(os.path.abspath(cur_dir + '/graph'))
sys.path.append(os.path.abspath(cur_dir + '/function'))
sys.path.append(os.path.abspath(cur_dir + '/maxsum'))
sys.path.append(os.path.abspath(cur_dir + '/system'))
sys.path.append(os.path.abspath(cur_dir + '/solver'))

from DataGenerator import DataSet
from NodeFunction import NodeFunction
from TabularFunction import TabularFunction
from Agent import Agent
from NodeVariable import NodeVariable
from NodeFunction import NodeFunction
from NodeArgument import NodeArgument
from COP_Instance import COP_Instance
from MaxSum import MaxSum

class DcopAllocator:

    def __init__(self, p_graph, logger, collab=False, tighten_schedule=False, use_prio=False):
        self._p_graph = p_graph
        self._cost_table = {} # { task_id : { robot_id : (cost, stn_pos) } }
        self.logger = logger
        self._tasks_preconditions = {}
        self._collab = collab
        self._tighten_schedule = tighten_schedule 
        self._use_prio = use_prio

    def allocate(self, robots, is_hetero=False):        
        n = self._p_graph.size()

        while True:
            ts = self._p_graph.scheduled_nodes
            tf = self._p_graph.first_layer
            tl = self._p_graph.second_layer

            self.logger.debug("{0} tasks have been scheduled.".format(len(ts)))
            self.logger.debug("First layer contains {0} tasks.".format(len(tf)))
            self.logger.debug("Second layer contains {0} tasks.".format(len(tl))) 

            if len(ts) >= n:
                self.logger.debug("All tasks have been scheduled.")
                break

            batch = set([node.task for node in tf])
            if self._use_prio:
                c = max([ node.priority for node in tl ]) if tl else 0
                batch = set([ node.task for node in tf if node.priority > c ])
                        
            cur_tasks = deepcopy(batch)
            while len(cur_tasks) > 0:
                self._cost_table = {}
                self.logger.debug("Creating dcop for {0} tasks.".format(len(cur_tasks)))
                for task in cur_tasks:
                    self.logger.debug(str(task))

                dcop = self.create_dcop(cur_tasks, robots, is_hetero)                                 
                self.logger.debug("Dcop created. Now solving dcop.")
                self.logger.debug("Cost Table: {0}".format(str(self._cost_table)))
                
                if dcop is None:
                    cur_tasks.clear()
                    print("Tasks cannot be allocated.")
                    break    
                
                ms = self.solve_dcop(dcop, test)
                results = ms.get_results()
                self.logger.debug("Dcop solved.")

                if len(results) == 0:
                    cur_tasks.clear()
                    print("Tasks cannot be allocated.")
                    break                                            

                scheduled_tasks = set()
                task_ids = set(results.values())

                if len([t for t in task_ids if t != 0]) == 0:
                    print "All zeros. Should not happen"
                    sys.exit(0)

                for task_id in task_ids:
                    if task_id > 0: 
                        robot_ids = [r for r,t in results.iteritems() if t == task_id]
                        if not self._collab:
                            robot_ids = [robot_ids[-1]]
                        
                        for robot_id in robot_ids:
                            self.logger.debug("Task {0} has been assigned to robot {1}".format(task_id, robot_id))
                            robot = [robot for robot in robots if robot.id == robot_id][0]
                            scheduled_task = [task for task in cur_tasks if task.id == task_id][0]
                            pos = self._cost_table[scheduled_task.id][robot.id][1]
                            self.logger.debug("Adding task {0} to robot {1}'s STN at position {2}".format(task_id, robot_id, pos))
                            robot.add_task(scheduled_task, pos, self._tasks_preconditions)
                            self.logger.debug("Task has been added.")
                            scheduled_tasks.add(scheduled_task)
                
                cur_tasks = cur_tasks.difference(scheduled_tasks)  #remove scheduled tasks

            for robot in robots:
                tasks = set()
                if self._tighten_schedule:
                    tasks = robot.tighten_schedule()                                       
                else:                    
                    tasks = robot.stn.get_all_tasks()

                self._p_graph.update_tasks(tasks)
                self.logger.debug("Robot {0}: Makespan is {1}".format(robot.id, robot.stn.get_makespan()))
                self.logger.debug("\nRobot {0}: Schedule:\n {1}\n".format(robot.id, str(robot.stn)))
            
            for task in batch:                
                self.logger.debug("Updating precedence graph for task {0}".format(task.id))
                pc = self._p_graph.update(task)  
                for k,v in pc.iteritems():
                    self._tasks_preconditions[k] = v 
                self.logger.debug("Precedence graph updated.")  

        schedules = []
        for robot in robots:
            schedules.append(robot.stn)

        return schedules           

    def solve_dcop(self, dcop):
        ms = MaxSum(dcop, "max")
        ms.setUpdateOnlyAtEnd(False) 
        ms.setIterationsNumber(3)
        ms.solve_complete()
        return ms

    def create_dcop(self, tasks, robots, is_hetero):
        variables = set()        
        functions = { }
        agents = [Agent(robot.id) for robot in robots]        

        for task in tasks:
            function = NodeFunction(task.id)
            function.setFunction(TabularFunction())
            functions[task.id] = function
            random.choice(agents).addNodeFunction(function)

        for robot in robots:        
            variable = NodeVariable(robot.id)            
            domain = []

            for task in tasks:
                if is_hetero and not robot.is_capable(task):
                    continue

                min_cost, min_pos = robot.find_min_cost(task, self._tasks_preconditions)
                if task.id in self._cost_table:
                    self._cost_table[task.id][robot.id] = (1/min_cost, min_pos)
                else:
                    self._cost_table[task.id] = {robot.id: (1/min_cost, min_pos)}

                #if robot can fit this task in its schedule
                if min_cost < float("inf"):
                    function = functions[task.id]
                    domain.append(function.function_id)                    
                    variable.addNeighbour(function)
                    function.addNeighbour(variable)

            #if robot can do atleast one task
            if len(domain) > 0:                
                domain = domain + [-func_id for func_id in domain]                                
                variable.addDomain(domain)
                variables.add(variable)
                agent = [agent for agent in agents if agent.agent_id == robot.id][0]
                agent.addNodeVariable(variable)    

        for _, function in functions.iteritems():
            size = len(function.params)                        
            if size > 0:
                func_id = function.function_id                                  
                all_values = list(product(*[(func_id, -func_id)] * size))          
                
                for values in all_values:
                    func_args = [NodeArgument(v) for v in values]                                                                                        
                    utility = self._calc_function_utility(function, func_args)
                    function.getFunction().addParametersCost(func_args, utility)
                    
        if len(variables) == 0:            
            return None

        dcop = COP_Instance(variables, list(functions.values()), agents)
        return dcop

    def _calc_function_utility(self, function, func_args):
        robot_cost_arr = []
        i = 0

        func_id = function.function_id
        while i < len(func_args):             
            if func_args[i].value == func_id:
                robot_variable = function.params[i]
                robot_cost = self._cost_table[func_id][robot_variable.id_var][0]
                robot_cost_arr.append(robot_cost)
            i += 1

        function_utility = -10000000

        num_of_robots = len(robot_cost_arr)
        if self._collab:
            if num_of_robots > 0:
                total_cost = self._calc_combined_cost(robot_cost_arr)
                function_utility = math.log(total_cost)
        elif num_of_robots == 1:
                total_cost = self._calc_combined_cost(robot_cost_arr)
                function_utility = total_cost

        return function_utility

    def _calc_combined_cost(self, robot_cost_arr):
        return sum(robot_cost_arr)/float(len(robot_cost_arr))

