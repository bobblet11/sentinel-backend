import psutil

from common.io.units import bytes_to_human_readable
from common.io.utils import prCyan, prGreen


def get_sys_cpu_stats():
    """
    Gathers and returns a dictionary of system CPU statistics.
    """
    logical_core_count = psutil.cpu_count(logical=True)
    physical_core_count = psutil.cpu_count(logical=False)

    # Get total CPU times and stats, and convert them to dictionaries
    total_cpu_times = psutil.cpu_times(percpu=False)
    total_cpu_stats_nt = psutil.cpu_stats()
    total_cpu_percent = psutil.cpu_percent(interval=1.0, percpu=False)

    total_cpu_stats = {
        **total_cpu_times._asdict(),
        **total_cpu_stats_nt._asdict(),
        "percent": total_cpu_percent,
    }

    # Get individual CPU times and usage percentages
    individual_cpu_times = psutil.cpu_times(percpu=True)
    individual_cpu_percent = psutil.cpu_percent(interval=1.0, percpu=True)

    individual_cpu_stats = []
    for i in range(len(individual_cpu_times)):
        cpu_stat = {
            "times": individual_cpu_times[i]._asdict(),
            "percent": individual_cpu_percent[i],
        }
        individual_cpu_stats.append(cpu_stat)

    cpu_stats = {
        "logical_core_count": logical_core_count,
        "physical_core_count": physical_core_count,
        "total_cpu_stats": total_cpu_stats,
        "individual_cpu_stats": individual_cpu_stats,
    }

    return cpu_stats


def get_sys_mem_stats():
    return {
        "ram": psutil.virtual_memory()._asdict(),
        "swap": psutil.swap_memory()._asdict(),
    }


def get_sys_network_stats():
    return {
        "net_io_counters": psutil.net_io_counters(pernic=False, nowrap=True)._asdict()
    }


def get_sys_stats():
    try:
        return {
            "cpu": get_sys_cpu_stats(),
            "memory": get_sys_mem_stats(),
            "network": get_sys_network_stats(),
        }

    except Exception as e:
        print(e)


def format_sys_stats(stats):
    """
    Takes a dictionary of system stats and returns a formatted string.
    """
    if not stats:
        return "Could not retrieve system stats."

    output = []

    # --- CPU Statistics ---
    cpu_stats = stats.get("cpu", {})
    output.append(prCyan(f"\n{'=' * 20} CPU Statistics {'=' * 20}"))
    output.append(f"  Physical Cores: {cpu_stats.get('physical_core_count')}")
    output.append(f"  Logical Cores:  {cpu_stats.get('logical_core_count')}")
    total_cpu = cpu_stats.get("total_cpu_stats", {})
    output.append(
        prGreen(f"  Total CPU Utilization: {total_cpu.get('percent', 'N/A')}%")
    )
    individual_cpu = cpu_stats.get("individual_cpu_stats", [])

    for i, cpu in enumerate(individual_cpu):
        cpu_times = cpu.get(
            "times", {"user": "N/A", "system": "N/A", "idle": "N/A", "iowait": "N/A"}
        )
        percent = cpu.get("percent", "N/A")
        user_time = cpu_times.get("user", "N/A")
        sys_time = cpu_times.get("system", "N/A")
        idle_time = cpu_times.get("idle", "N/A")
        io_time = cpu_times.get("iowait", "N/A")
        output.append(f"\n{'=' * 19} CPU Core {i} {'=' * 18}")
        output.append(f"\tUser time  : {user_time} s")
        output.append(f"\tSystem time: {sys_time} s")
        output.append(f"\tIdle time  : {idle_time} s")
        output.append(f"\tIO wait    : {io_time} s")

        output.append(f"\tPercent    : {percent} %")
        output.append(f"{'=' * 49}\n")

    # --- Memory Statistics ---
    mem_stats = stats.get("memory", {})
    ram = mem_stats.get("ram", {})
    swap = mem_stats.get("swap", {})
    output.append(prCyan(f"\n{'=' * 20} Memory Statistics {'=' * 18}"))
    if ram:
        output.append("  RAM:")
        output.append(f"    Total:     {bytes_to_human_readable(ram.get('total', 0))}")
        output.append(
            f"    Available: {bytes_to_human_readable(ram.get('available', 0))}"
        )
        output.append(f"    Used:      {bytes_to_human_readable(ram.get('used', 0))}")
        output.append(prGreen(f"    Usage:     {ram.get('percent', 'N/A')}%"))
    if swap:
        output.append("  Swap:")
        output.append(f"    Total:     {bytes_to_human_readable(swap.get('total', 0))}")
        output.append(f"    Free:      {bytes_to_human_readable(swap.get('free', 0))}")
        output.append(f"    Used:      {bytes_to_human_readable(swap.get('used', 0))}")
        output.append(prGreen(f"    Usage:     {swap.get('percent', 'N/A')}%"))

    # --- Network Statistics ---
    net_stats = stats.get("network", {}).get("net_io_counters", {})
    output.append(prCyan(f"\n{'=' * 20} Network Statistics {'=' * 17}"))
    if net_stats:
        output.append(
            f"  Bytes Sent:     {bytes_to_human_readable(net_stats.get('bytes_sent', 0))}"
        )
        output.append(
            f"  Bytes Received: {bytes_to_human_readable(net_stats.get('bytes_recv', 0))}"
        )
        output.append(f"  Packets Sent:   {net_stats.get('packets_sent', 0):,}")
        output.append(f"  Packets Recv:   {net_stats.get('packets_recv', 0):,}")

    output.append("\n\n\n")
    return "\n".join(output)


print(format_sys_stats(get_sys_stats()))
