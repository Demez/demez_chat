import os
import sys
import argparse

from time import sleep, perf_counter
import inspect

import cProfile, pstats, io
from pstats import SortKey

from PyQt5.QtWidgets import *
from PyQt5.QtCore import *
from PyQt5.QtGui import *

# to load mpv-1.dll or libmpv.dll.a from the thirdparty folder
os.environ["PATH"] = os.path.dirname(__file__) + os.sep + "thirdparty" + os.pathsep + os.environ["PATH"]

from api2.thirdparty import mpv


# MPV COMMANDS: https://mpv.io/manual/master/#list-of-input-commands


# duration times this for slider values
# increase for more accurate slider positions, though 10 is fine all around
# i would do frames, but i can't find that in libmpv currently
TIME_MULT = 1
MAX_VOLUME = 100


def dict_to_str(dictionary: dict, depth: int = 0) -> str:
    final_value = ""
    space = "{0}".format(depth * " ")
    for key, value in dictionary.items():
        value_type = type(value)
        
        try:
            value = dict_to_str(value.__dict__, depth + 1)
            final_value += f'{space}"{key}"\n{space}{{\n{value}\n{space}}}"'
        except Exception as F:
            print(str(F))
            
            if value and type(value) == dict:
                value = dict_to_str(value, depth + 1)
                final_value += f'{space}"{key}"\n{space}{{\n{value}\n{space}}}"'
            else:
                final_value += f'{space}"{key}" "{value}"'
                
    return final_value
    
    
class VideoContainer(QWidget):
    def __init__(self, player):
        super().__init__(player)
        self.player = player
        layout = QVBoxLayout()
        self.setLayout(layout)
        self.setMinimumHeight(400)
        # self.layout().addWidget(QLabel("Ready to Play Video"))
    
    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.LeftButton:
            self.player.playback_toggle()
    
    
class VideoProgress(QSlider):
    def __init__(self, player):
        super().__init__(Qt.Horizontal)
        self.player = player
        self.moved = False
        self.locked = False
        
    def slider_update(self, progress: int) -> None:
        if not self.locked:
            self.blockSignals(True)
            self.setValue(progress)
            self.blockSignals(False)
        
    def slider_user_update(self, event: QMouseEvent) -> None:
        if self.player.has_video():
            # both work fine
            # self.setValue(QStyle.sliderValueFromPosition(self.minimum(), self.maximum(), event.x(), self.width()))
            value = self.minimum() + ((self.maximum() - self.minimum()) * event.x()) / self.width()
            self.setValue(int(self.minimum() + ((self.maximum() - self.minimum()) * event.x()) / self.width()))
    
    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.LeftButton:
            self.locked = True
            self.slider_user_update(event)
            event.accept()
            self.locked = False
    
    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.LeftToRight:
            self.locked = True
            self.slider_user_update(event)
            event.accept()
    
    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        button = event.button()
        if event.button() == Qt.LeftButton:
            self.locked = False
            event.accept()
        

class VideoPlayer(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        
        main_layout = QVBoxLayout()
        main_layout.setContentsMargins(0, 0, 0, 0)
        # main_widget = QWidget(self)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        
        self.player_widget = VideoContainer(self)
        self.player_widget.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

        self.position_slider = VideoProgress(self)
        self.position_slider.sliderPressed.connect(self.playback_toggle_slider)
        self.position_slider.sliderReleased.connect(self.playback_toggle_slider)
        # self.position_slider.sliderMoved.connect(self.slider_seek)
        self.position_slider.valueChanged.connect(self.slider_seek)
        
        self.position_thread = VideoPosition(self)
        
        playback_button_widget = QWidget()
        playback_button_layout = QHBoxLayout()
        
        self.btn_toggle_playback = QPushButton(">")
        self.btn_frame_prev = QPushButton("<|")
        self.btn_frame_next = QPushButton("|>")
        self.volume_slider = QSlider(Qt.Horizontal)
        
        self.btn_toggle_playback.pressed.connect(self.playback_toggle)
        self.btn_frame_prev.pressed.connect(self._prev_frame)
        self.btn_frame_next.pressed.connect(self._next_frame)
        self.volume_slider.valueChanged.connect(self.change_volume)
        self.volume_slider.setRange(0, 130)

        playback_button_widget.setLayout(playback_button_layout)
        playback_button_layout.addWidget(self.btn_toggle_playback)
        playback_button_layout.addWidget(self.btn_frame_prev)
        playback_button_layout.addWidget(self.btn_frame_next)
        playback_button_layout.addWidget(self.volume_slider)
        playback_button_layout.addStretch(0)

        # playback_button_layout.setContentsMargins(0, 0, 0, 0)
        playback_button_layout.setContentsMargins(8, 0, 8, 8)
        
        self.setLayout(main_layout)

        # main_widget.setLayout(main_layout)
        # main_layout.addWidget(main_widget)
        main_layout.addWidget(self.player_widget)
        # main_layout.addStretch(0)
        main_layout.addWidget(self.position_slider)
        main_layout.addWidget(playback_button_widget)

        self.selected_video = None
        self.current_video = None
        self.file_dialog = None
        self.duration = None
        
        self.player = mpv.MPV(wid=str(int(self.player_widget.winId())),
                              # vo='x11', # You may not need this
                              # log_handler=print, loglevel='debug'  # , options={"--volume-max", "400"}
                              )
        
        self.player.keep_open = True
        
        # volume: self.player.properties["volume"]
        
        # self.setAcceptDrops(True)
        self.show()
        
    def __del__(self):
        self.player.quit()
        del self.player
    
    def set_video_path(self, video_path: str):
        self.selected_video = video_path
        
    def dropEvent(self, event: QDropEvent):
        text = event.mimeData().text()
        header = ""
        if text.startswith("file:///"):
            header = "file:///"
            
        self.load_video(text[len(header):])

    def dragEnterEvent(self, event: QDragEnterEvent) -> None:
        text = event.mimeData().text()
        if text.startswith("file:///"):
            event.accept()
        elif text.startswith("https://") or text.startswith("ftp://"):
            event.accept()
        
    def load_video(self, video_path: str, start_playback: bool = False) -> None:
        self.selected_video = video_path
        self.current_video = video_path
        
        if not self.has_video():
            self.btn_toggle_playback.setText("||")
            
        # self.player.play(video_path)
        self.player.loadfile(video_path)
        frame_count = 0
        index = 0
        while frame_count == 0:
            if not self.has_video():
                self.btn_toggle_playback.setText(">")
                return
            sleep(0.1)
            frame_count = self.player.estimated_frame_count
            
        if start_playback and self.player.pause:
            self.player.command("cycle", "pause")
        
        self.player.observe_property("ao-volume", self.position_slider.slider_update)
            
        self.position_slider.setValue(0)
        if frame_count is not None:
            self.position_slider.setRange(0, frame_count)
        self.position_thread.start()
        
        # volume = self.get_volume()
        # self.volume_slider.setValue(volume)
        # self.volume_slider.setValue(100)
        
    def playback_toggle_slider(self, *uh) -> None:
        if self.get_video():
            self.player.command("seek", str(self.position_slider.value()), "absolute")
            if not self.player.pause:
                self.player.command("cycle", "pause")
                self.btn_toggle_playback.setText(">")
            else:
                self.btn_toggle_playback.setText(">")
        
    def playback_toggle(self, *uh) -> None:
        if self.selected_video and not self.current_video:
            self.load_video(self.selected_video)
        if self.get_video():
            self.player.command("cycle", "pause")
            text = ">" if self.player.pause else "||"
            self.btn_toggle_playback.setText(text)
        
    def pause_video(self, *uh) -> None:
        if self.get_video() and not self.player.pause:
            self.player.command("cycle", "pause")
            self.btn_toggle_playback.setText(">")
        
    def resume_video(self, *uh) -> None:
        if self.get_video() and self.player.pause:
            self.player.command("cycle", "pause")
            self.btn_toggle_playback.setText("||")
        
    def slider_seek(self, value: int) -> None:
        try:
            pass
            if self.get_video():
                new_time = self.get_seconds_from_frames(value)
                self.player.command("seek", str(new_time), "absolute")
        except SystemError:
            print("video over")
        
    def get_seconds_from_frames(self, frame_number: int) -> int:
        return frame_number / self.player.display_fps if self.player.display_fps is not None else 0
        
    def get_total_frames(self) -> int:
        pass
    
    def get_current_frame(self) -> int:
        return self.player.player.estimated_frame_number
        
    def has_video(self) -> bool:
        return bool(self.get_video())
        
    def get_video(self) -> str:
        return self.player.media_title
        
    # def get_playlist(self) -> bool:
    #     return self.player.playlist_filenames
    
    def _next_frame(self, *uh):
        self.player.command("frame-step")
    
    def _prev_frame(self, *uh):
        self.player.command("frame-back-step")
    
    def get_volume(self, *uh):
        if self.has_video():
            # return self.player.command("get_property", "ao-volume")
            return self.player.observe_property("ao-volume", )
    
    def set_volume(self, volume):
        if self.has_video():
            return self.player.command("set_property", "ao-volume", str(volume))
    
    def change_volume(self, volume: int) -> None:
        if self.has_video():
            self.player.command("set", "ao-volume", str(min(volume, MAX_VOLUME)))


class VideoPosition(QTimer):
    def __init__(self, player: VideoPlayer):
        super().__init__(player)
        self.player = player
        self.exiting = False
        self.timeout.connect(self.update_scroll)
    
    def update_scroll(self):
        if self.player.has_video() and not self.player.player.pause:
            try:
                # progress = self.player.player.time_pos
                progress = self.player.player.estimated_frame_number
            except TypeError:
                return
            if progress:
                self.player.position_slider.slider_update(progress)




