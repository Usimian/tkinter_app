import tkinter as tk
from tkinter import ttk, messagebox
import cv2
from PIL import Image, ImageTk
import matplotlib.pyplot as plt
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
import psutil
import matplotlib
import logging
from contextlib import contextmanager
import GPUtil  # Add this import for GPU monitoring

matplotlib.use('TkAgg')


# Custom exceptions
class CameraError(Exception):
    """Raised when camera operations fail"""
    pass


class ResourceError(Exception):
    """Raised when system resource monitoring fails"""
    pass


class App:
    def __init__(self, root):
        # Configure logging
        logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
        self.logger = logging.getLogger(__name__)

        try:
            self.root = root
            self.root.title("Camera Feed")
            self.root.geometry("450x670")  # Increased height to accommodate GPU load

            # Configure root window grid
            self.root.grid_rowconfigure(0, weight=1)
            self.root.grid_columnconfigure(0, weight=1)

            # Variables to store scheduled task IDs with validation
            self._cancel_scheduled_tasks()
            self.video_task = None
            self.memory_task = None
            self.cpu_task = None
            self.gpu_task = None  # Add GPU task

            # Flag to track if the application is running
            self.running = True

            # Bind cleanup with error handling
            self.root.protocol("WM_DELETE_WINDOW", self._safe_cleanup)

            self.logger.info("Application initialized successfully")

        except tk.TclError as e:
            self.logger.error(f"Failed to initialize window: {e}")
            messagebox.showerror("Error", "Failed to initialize application")
            raise

        # Create main frame
        self.main_frame = ttk.Frame(self.root, padding="10")
        self.main_frame.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))

        # Configure main frame grid
        self.main_frame.grid_rowconfigure(0, weight=1)
        self.main_frame.grid_columnconfigure(0, weight=1)

        # Create video container frame with white border
        self.video_frame = tk.Frame(self.main_frame, background='white')
        self.video_frame.grid(row=0, column=0, pady=(0, 10), sticky=(tk.W, tk.E, tk.N, tk.S))
        self.video_frame.grid_rowconfigure(0, weight=1)
        self.video_frame.grid_columnconfigure(0, weight=1)

        # Create video label with small padding to show red border and center it
        self.video_label = ttk.Label(self.video_frame, padding=2)
        self.video_label.place(relx=0.5, rely=0.5, anchor=tk.CENTER)

        # Create figure for pie chart
        self.fig, self.ax = plt.subplots(figsize=(4, 3))
        self.canvas = FigureCanvasTkAgg(self.fig, master=self.main_frame)
        self.canvas.get_tk_widget().grid(row=1, column=0, pady=(0, 10))

        # Create CPU load frame and widgets
        self.cpu_frame = ttk.Frame(self.main_frame)
        self.cpu_frame.grid(row=2, column=0, pady=(0, 10), sticky='ew')

        self.cpu_label = ttk.Label(self.cpu_frame, text="CPU Load: 0%",
                                   font=('Arial', 12))
        self.cpu_label.grid(row=0, column=0, padx=(0, 10))

        self.cpu_bar = ttk.Progressbar(self.cpu_frame, length=200,
                                       mode='determinate',
                                       style='CPU.Horizontal.TProgressbar')
        self.cpu_bar.grid(row=0, column=1, sticky='ew')

        # Create GPU load frame and widgets
        self.gpu_frame = ttk.Frame(self.main_frame)
        self.gpu_frame.grid(row=3, column=0, pady=(0, 10), sticky='ew')

        self.gpu_label = ttk.Label(self.gpu_frame, text="GPU Load: N/A",
                                  font=('Arial', 12))
        self.gpu_label.grid(row=0, column=0, padx=(0, 10))

        self.gpu_bar = ttk.Progressbar(self.gpu_frame, length=200,
                                      mode='determinate',
                                      style='GPU.Horizontal.TProgressbar')
        self.gpu_bar.grid(row=0, column=1, sticky='ew')

        # Configure progress bar styles
        style = ttk.Style()
        style.configure('CPU.Horizontal.TProgressbar',
                        troughcolor='#E0E0E0',
                        background='#2196F3')
        style.configure('GPU.Horizontal.TProgressbar',
                        troughcolor='#E0E0E0',
                        background='#4CAF50')  # Green for GPU

        # Initialize video capture
        self.cap = cv2.VideoCapture(0)
        if not self.cap.isOpened():
            print("Error: Could not open camera")
        else:
            self.update_video()
            self.update_memory_chart()
            self.update_cpu_load()
            self.update_gpu_load()  # Start GPU monitoring

    def _cancel_scheduled_tasks(self):
        """Cancel all scheduled tasks"""
        for attribute in ('video_task', 'memory_task', 'cpu_task', 'gpu_task'):
            task_id = getattr(self, attribute, None)
            if task_id:
                self.root.after_cancel(task_id)

    @contextmanager
    def error_handler(self, operation):
        """Context manager for handling operations with proper error logging"""
        try:
            yield
        except Exception as e:
            self.logger.error(f"Error during {operation}: {e}")
            messagebox.showerror("Error", f"An error occurred during {operation}")
            raise

    def update_video(self):
        if not self.running:
            return
        ret, frame = self.cap.read()
        if ret:
            # Convert frame from BGR to RGB
            frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            
            # Get current window size
            window_width = self.video_frame.winfo_width()
            window_height = self.video_frame.winfo_height()
            
            # Ensure minimum size
            target_width = max(320, window_width - 4)  # -4 for padding
            target_height = max(240, window_height - 4)  # -4 for padding
            
            # Calculate aspect ratio
            aspect_ratio = 4/3  # Standard webcam aspect ratio
            
            # Adjust dimensions to maintain aspect ratio
            if target_width/target_height > aspect_ratio:
                target_width = int(target_height * aspect_ratio)
            else:
                target_height = int(target_width / aspect_ratio)
            
            # Convert to PIL Image
            image = Image.fromarray(frame)
            # Flip the image horizontally
            image = image.transpose(Image.Transpose.FLIP_LEFT_RIGHT)
            # Resize image maintaining aspect ratio
            image = image.resize((target_width, target_height), Image.Resampling.LANCZOS)
            # Convert to PhotoImage
            photo = ImageTk.PhotoImage(image=image)
            # Update label
            self.video_label.configure(image=photo)
            self.video_label.image = photo
            
        # Schedule the next update
        if self.running:
            self.video_task = self.root.after(10, self.update_video)

    def update_memory_chart(self):
        if not self.running:
            return
        # Clear previous plot
        self.ax.clear()

        # Get memory info
        memory = psutil.virtual_memory()
        used = memory.used / (1024 * 1024 * 1024)  # Convert to GB
        available = memory.available / (1024 * 1024 * 1024)  # Convert to GB

        # Create pie chart
        sizes = [used, available]
        labels = [f'Used\n{used:.1f} GB', f'Available\n{available:.1f} GB']
        colors = ['#ff9999', '#66b3ff']

        self.ax.pie(sizes, labels=labels, colors=colors, autopct='%1.1f%%',
                    startangle=90)
        self.ax.axis('equal')
        self.fig.suptitle('Memory Usage', y=0.95)

        # Redraw canvas
        self.canvas.draw()

        # Schedule next update
        if self.running:
            self.memory_task = self.root.after(1000, self.update_memory_chart)

    def update_cpu_load(self):
        if not self.running:
            return
        try:
            # Get CPU usage percentage (averaged across all cores)
            cpu_percent = psutil.cpu_percent(interval=None)
            # Get CPU frequency
            cpu_freq = psutil.cpu_freq().current / 1000  # Convert MHz to GHz

            # Update progress bar and label
            self.cpu_bar['value'] = cpu_percent
            self.cpu_label.config(text=f"CPU Load: {cpu_percent:.1f}% ({cpu_freq:.2f} GHz)")

            # Change progress bar color based on CPU load
            style = ttk.Style()
            if cpu_percent > 80:
                style.configure('CPU.Horizontal.TProgressbar',background='#FF5252')  # Red
            elif cpu_percent > 60:
                style.configure('CPU.Horizontal.TProgressbar',background='#FFA726')  # Orange
            else:
                style.configure('CPU.Horizontal.TProgressbar',background='#2196F3')  # Blue

        except Exception as e:
            print(f"Error reading CPU load: {e}")
            self.cpu_label.config(text="CPU Load: Error")
            self.cpu_bar['value'] = 0

        # Schedule next update
        if self.running:
            self.cpu_task = self.root.after(1000, self.update_cpu_load)

    def update_gpu_load(self):
        """Update GPU load information"""
        if not self.running:
            return
            
        try:
            # Try to get GPU information
            gpus = GPUtil.getGPUs()
            
            if gpus:
                # Get the first GPU
                gpu = gpus[0]
                gpu_load = gpu.load * 100  # Convert to percentage
                gpu_memory = gpu.memoryUsed
                gpu_temp = gpu.temperature
                
                # Update progress bar and label
                self.gpu_bar['value'] = gpu_load
                self.gpu_label.config(text=f"GPU Load: {gpu_load:.1f}% ({gpu_memory:.0f}MB, {gpu_temp}°C)")
                
                # Change progress bar color based on GPU load
                style = ttk.Style()
                if gpu_load > 80:
                    style.configure('GPU.Horizontal.TProgressbar', background='#FF5252')  # Red
                elif gpu_load > 60:
                    style.configure('GPU.Horizontal.TProgressbar', background='#FFA726')  # Orange
                else:
                    style.configure('GPU.Horizontal.TProgressbar', background='#4CAF50')  # Green
            else:
                self.gpu_label.config(text="GPU: Not detected")
                self.gpu_bar['value'] = 0
                
        except Exception as e:
            self.logger.error(f"Error reading GPU load: {e}")
            self.gpu_label.config(text="GPU Load: Error")
            self.gpu_bar['value'] = 0
            
        # Schedule next update
        if self.running:
            self.gpu_task = self.root.after(1000, self.update_gpu_load)

    def _safe_cleanup(self):
        """Safely cleanup resources with error handling"""
        try:
            self._stop_all_tasks()
            if self.root.winfo_exists():
                self.root.destroy()
        except Exception as exc:
            self._handle_cleanup_error(exc)

    def _stop_all_tasks(self):
        """Stop all scheduled tasks"""
        for task_id in (self.video_task, self.memory_task, self.cpu_task, self.gpu_task):
            if task_id:
                self.root.after_cancel(task_id)

    def _handle_cleanup_error(self, exc):
        """Handle any errors that occur during cleanup"""
        self.logger.error(f"Error during cleanup: {exc}")

    def cleanup(self):
        """Graceful cleanup of all resources"""
        try:
            # Set running flag to False first to stop all update loops
            self.running = False

            # Cancel all scheduled tasks
            if hasattr(self, 'video_task') and self.video_task:
                self.root.after_cancel(self.video_task)
            if hasattr(self, 'memory_task') and self.memory_task:
                self.root.after_cancel(self.memory_task)
            if hasattr(self, 'cpu_task') and self.cpu_task:
                self.root.after_cancel(self.cpu_task)
            if hasattr(self, 'gpu_task') and self.gpu_task:
                self.root.after_cancel(self.gpu_task)

            # Release camera with check
            if hasattr(self, 'cap') and self.cap and self.cap.isOpened():
                self.cap.release()

            # Close matplotlib resources
            if hasattr(self, 'fig'):
                plt.close(self.fig)

            # Clear any remaining tasks
            for task in self.root.tk.call('after', 'info'):
                self.root.after_cancel(task)

            # Finally destroy the window
            self.root.quit()
            self.root.destroy()

        except Exception as e:
            print(f"Error during cleanup: {e}")
            # Force quit if cleanup fails
            self.root.quit()
            self.root.destroy()

    def __del__(self):
        """Destructor to ensure camera is released"""
        if hasattr(self, 'cap') and self.cap and self.cap.isOpened():
            self.cap.release()


def main():
    """Main entry point for the application"""
    root_window = tk.Tk()
    app = App(root_window)
    root_window.protocol("WM_DELETE_WINDOW", app.cleanup)
    root_window.mainloop()


if __name__ == "__main__":
    main()
