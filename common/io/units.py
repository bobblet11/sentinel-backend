def bytes_to_human_readable(n_bytes):
        """Converts a number of bytes into a human-readable format (GB, MB, KB)."""
        if n_bytes > 1024**3:
                return f"{n_bytes / 1024**3:.2f} GB"
        elif n_bytes > 1024**2:
                return f"{n_bytes / 1024**2:.2f} MB"
        elif n_bytes > 1024:
                return f"{n_bytes / 1024:.2f} KB"
        else:
                return f"{n_bytes} B"
