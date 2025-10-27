import psutil
import os
from common.io.redirect_and_modify import redirect_and_modify, prRed, prGreen, prCyan

@redirect_and_modify(string_modification_function=prRed)
def print_sys_cpu_stats():
	logical_core_count = psutil.cpu_count(logical=True)
	physical_core_count = psutil.cpu_count(logical=False)
	cpu_times_list = psutil.cpu_times(percpu=False)
	cpus_times_list = psutil.cpu_times(percpu=True)
	cpus_usage_percent_list = psutil.cpu_percent(interval=1.0, percpu=True)
	ctx_switches, interrupts, soft_interrupts, syscalls, *remaining = psutil.cpu_stats()

	print(f"\n\n{"-" * 15} CPU Statistics {"-" * 15}")
	print(f"Logical CPU cores: {logical_core_count}")
	print(f"Physical CPU cores: {physical_core_count}")	

	print(f"Total Utilization: {sum(cpus_usage_percent_list)} %")

	print(f"Total Time Distribution")
	print(f"\tUser: {cpu_times_list.user} s")
	print(f"\tSystem: {cpu_times_list.system} s")
	print(f"\tIdle: {cpu_times_list.idle} s")
	print(f"\tIO Wait: {cpu_times_list.iowait} s\n")

	print(f"No. Context Switches: {ctx_switches}")
	print(f"No. Interrupts: {interrupts}")
	print(f"No. Soft Interrupts: {soft_interrupts}")
	print(f"No. Syscalls: {syscalls}\n\n")

	for i in range(logical_core_count):
		user, system, idle, iowait, *remaining = cpus_times_list[i]
		print(f"\t{"-" * 10}CPU {i} Statistics {"-" * 10}")
		print(f"\tUtilization: {cpus_usage_percent_list[i]} %\n")
		print(f"\tTime Distribution")
		print(f"\t\tUser: {user} s")
		print(f"\t\tSystem: {system} s")
		print(f"\t\tIdle: {idle} s")
		print(f"\t\tIO Wait: {iowait} s\n\n")
        
@redirect_and_modify(string_modification_function=prGreen)
def print_sys_mem_stats():
	ram  = psutil.virtual_memory()
	swap = psutil.swap_memory()

	print(f"\n\n{"-" * 15} Memory Statistics {"-" * 15}")
	print(f"Total RAM: {ram.total} B")
	print(f"RAM utilization: {ram.percent} %")
	print(f"Used RAM: {ram.total - ram.available} B")
	print(f"Available RAM: {ram.available} B\n")
	print(f"Total Swap: {swap.total} B")
	print(f"Swap utilization: {swap.percent} %")
	print(f"Used Swap: {swap.used} B")
	print(f"Available Swap: {swap.free} B")
     
@redirect_and_modify(string_modification_function=prCyan)   
def print_sys_network_stats():
	bytes_sent, bytes_recv, packets_sent, packets_recv, *remaining = psutil.net_io_counters(pernic=False, nowrap=True)
	print(f"\n\n{"-" * 15} Network Statistics {"-" * 15}")
	print(f"Bytes Sent: {bytes_sent} B")
	print(f"Bytes Received: {bytes_recv} B")
	print(f"Packets Sent: {packets_sent}")
	print(f"Packets Received: {packets_recv}")
	
def print_sys_stats():
	try:
		print_sys_cpu_stats()
		print_sys_mem_stats()
		print_sys_network_stats()
	except Exception as e:
		print(e)

def print_current_process_stats():
        try:
                pass
        except psutil.Error as e:
                pass
        except Exception as e:
                pass
             
def print_specific_process_stats(pid:int):
        try:
                pass
        except psutil.Error as e:
                pass
        except Exception as e:
                pass

print_sys_stats()
