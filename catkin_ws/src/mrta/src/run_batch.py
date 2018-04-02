import os
import sys
import pickle
import argparse
from copy import deepcopy
from datetime import datetime
import utils
import psycopg2

cur_dir = os.path.dirname(os.path.realpath(__file__))
sys.path.append(os.path.abspath(cur_dir + "/PIA/"))
sys.path.append(os.path.abspath(cur_dir + "/DCOP"))

from PIA2 import PIA
from DcopAllocator import DcopAllocator
from Robot import Robot
from DataGenerator import DataGenerator, DataSet
from Logger import Logger, LogLevel

def execute_sql(conn, sql):
    cursor = conn.cursor()
    try:
        cursor.execute(sql)
    except psycopg2.Error as e:
        print("Database error occured while executing {0}".format(sql))
        print e.diag.message_primary
        sys.exit(0)

    conn.commit()
    cursor.close()    

def print_schedules(all_schedules1, all_schedules2):    
    i = 0
    while i < len(all_schedules1):        
         
        schedules1 = all_schedules1[i]
        j = 0
        print("\n-------------------------1---------------------------------\n")
        while j < len(schedules1):
            if schedules1[j].task_count > 0:
                print(str(schedules1[j]))
                print("\n")            
            j += 1
        
        if len(all_schedules2) > 0:
            schedules2 = all_schedules2[i]  
            print("\n------------------------------2----------------------------\n")
            j = 0
            while j < len(schedules2):
                if schedules2[j].task_count > 0:
                    print(str(schedules2[j]))
                    print("\n")
                j += 1
        
        i += 1

def calculate_stats(all_schedules):
    avg_makespan = 0
    avg_time_travelled = 0
    total_travel_time = 0
    total_make_span = 0

    total_tasks_scheduled = 0

    for schedules in all_schedules:
        all_tasks = set()
        makespan = float('-inf')        
        for stn in schedules:
            ms = stn.get_makespan()
            tt = stn.total_travel_time
            if ms > makespan:
                makespan = ms
            total_travel_time += tt
            all_tasks = all_tasks.union(stn.get_all_tasks())

        total_tasks_scheduled += len(all_tasks)
        total_make_span += makespan
        
    if len(all_schedules) != 0:
        avg_makespan = total_make_span / float(len(all_schedules))
        avg_time_travelled = total_travel_time / float(len(all_schedules))
        
        if avg_makespan == float("inf"):
            print("ERROR: Makespan can not be infinity.")
            sys.exit(0)

    return avg_makespan, avg_time_travelled, total_tasks_scheduled

def verify_no_collaboration(all_schedules):
    for schedules in all_schedules:  
        total_task = 0
        all_tasks = set()
        for stn in schedules:            
            tasks = set(stn.get_all_tasks())
            total_task += len(tasks)
            all_tasks = all_tasks.union(tasks)
        
        if total_task != len(all_tasks):
            print "Should not happen"
            print_schedules(all_schedules, None)
            sys.exit(0)    

def log_results(all_schedules1, all_schedules2, beta, alpha, task_count, robot_count, num_of_pgraphs, comment):
    ms1, tt1, st1 = calculate_stats(all_schedules1)
    ms2, tt2, st2 = calculate_stats(all_schedules2)
    
    print("Number of tasks scheduled: {0} and {1}".format(st1, st2))
    print("Average makespan: {0} and {1}".format(ms1, ms2))
    print("Average time travelled: {0} and {1}".format(tt1, tt2))             

    connect_str = "dbname='mrta' user='#' password='#' host='localhost'"
    conn = psycopg2.connect(connect_str)
   
    insert_record = """
                        INSERT INTO 
                            results(robots, tasks, pgraphs, alpha, beta, 
                                 ms1, tt1, scheduled_tasks1,
                                 ms2, tt2, scheduled_tasks2, last_updated, comment)
                        
                        VALUES('{0}', '{1}', '{2}', '{3}', '{4}', '{5}', '{6}', '{7}', '{8}', '{9}', '{10}', '{11}', '{12}')
                    """.format(robot_count, task_count, num_of_pgraphs, alpha, beta, ms1, tt1, st1, ms2, tt2, st2, datetime.now(), comment)

    execute_sql(conn, insert_record)

if __name__ == "__main__":    
    parser = argparse.ArgumentParser(description="MRTA Algorithms")

    parser.add_argument('-pgraphs',
        help='Number of precedence graphs',
        dest='num_of_pgraphs',
        type=int,
        default=5,
        action='store')

    robot_count_arr = [2, 4, 8]
    task_count_arr = [5, 10, 20, 30]
    alpha_arr = [0.25, 0.5, 0.75] 
    beta_arr = [0.25, 0.5, 0.75]
    map_x = 100
    map_y = 100

    args = parser.parse_args()
    num_of_pgraphs = args.num_of_pgraphs

    logger = Logger(LogLevel.OFF[0])

    dg = DataGenerator(map_x, map_y, logger)
    for robot_count in robot_count_arr:
        ori_robots =  dg.generate_robots(robot_count, 1)        
        for task_count in task_count_arr:
            max_possible_edges = (task_count * (task_count - 1))/2
            max_num_of_edges = min(3 * task_count, max_possible_edges)            
            for alpha in alpha_arr:
                for beta in beta_arr:
                    all_schedules1 = []
                    all_schedules2 = []

                    print("\n-------------------------------------------------------------")
                    print("Robot count: {0}".format(robot_count))
                    print("Task count: {0}".format(task_count))  
                    print("Precedence graph count: {0}".format(num_of_pgraphs))                  
                    print("Total Tasks: {0}".format(num_of_pgraphs * task_count))
                    print("Alpha: {0}".format(alpha))
                    print("Beta: {0}".format(beta))
                    
                    p_graphs = dg.generate_dataset(task_count, num_of_pgraphs, max_num_of_edges, beta)                                       
                    for p_graph in p_graphs:
                                                                       
                        dcop_robots = deepcopy(ori_robots)
                        for robot in dcop_robots:
                            robot.set_alpha(alpha)                                                                     
                        dcop = DcopAllocator(deepcopy(p_graph), logger, collab=False)                    
                        dcop_schedules = dcop.allocate(dcop_robots)
                        all_schedules1.append(dcop_schedules)     
                         
                        pia_robots = deepcopy(ori_robots)
                        for robot in pia_robots:
                            robot.set_alpha(alpha)   
                        pia = PIA(deepcopy(p_graph), pia_robots, logger)
                        pia_schedules = pia.allocate_tasks()
                        all_schedules2.append(pia_schedules)   

                    log_results(all_schedules1, all_schedules2, beta, alpha, task_count, robot_count, num_of_pgraphs, "040118")                                                  
                    print("-------------------------------------------------------------\n")
                                   
