import time
import cv2

from echolib import pyecho
import echocv

from threading import Thread, Lock


class EcholibWrapper:
    
    def __init__(self, model, out_channel, in_channel):

        self.loop   = pyecho.IOLoop()
        self.client = pyecho.Client()
        self.loop.add_handler(self.client)

        self.enabled = False

        self.dockerCommandOut = pyecho.Publisher(self.client, out_channel, "numpy.ndarray")
        self.dockerReady      = pyecho.Publisher(self.client, "containerReady", "int")

        self.dockerCommandIn  = pyecho.Subscriber(self.client, in_channel, "int", self.callback)
        self.dockerCameraIn   = pyecho.Subscriber(self.client, "cameraStream", "numpy.ndarray", self.cameraCallback)

        self.model = model

        self.frameInLock   = Lock()
        self.frameOutLock  = Lock()

        self.frameIn    = None
        self.frameInNew = False

        self.frameOut    = None
        self.frameOutNew = False 

        self.closing = False

    def callback(self, message):

        # TODO Maybe add some threading proctection?
        self.enabled = True if (pyecho.MessageReader(message).readInt() != 0) else False
        

    def cameraCallback(self, message):

        self.frameInLock.acquire()
        self.frameIn    = echocv.readMat(pyecho.MessageReader(message))
        self.frameInNew = True
        self.frameInLock.release()

    def process(self):
        
        # TODO Using self.closing in a thread unsafe manner
        while not self.closing:

            self.frameInLock.acquire()
            frame = None
            if self.frameInNew:
                frame = self.frameIn.copy()
                self.frameInNew = False
                self.frameInLock.release()

                # TODO Using enabled in a thread unsafe manner
                if self.enabled:
                    frame = cv2.cvtColor(frame, cv2.COLOR_RGB2BGR)
                    frame = self.model.doDetection(frame)
                    frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            else:
                self.frameInLock.release()

            if frame is not None:
                self.frameOutLock.acquire()
                self.frameOut    = frame
                self.frameOutNew = True
                self.frameOutLock.release()

    def run(self, wait_sec=10, sleep_sec=0):

        self.loop.wait(10) # Maybe registering subscribers and publishers?

        writer = pyecho.MessageWriter()
        writer.writeInt(1)
        self.dockerReady.send(writer)

        print("Starting thread...")

        thread = Thread(target = self.process)
        thread.start()

        while self.loop.wait(wait_sec):

            self.frameOutLock.acquire()
            if self.frameOutNew:
                writer = pyecho.MessageWriter()
                echocv.writeMat(writer, self.frameOut)
                self.dockerCommandOut.send(writer)

                self.frameOutNew = False
            self.frameOutLock.release()

            if sleep_sec > 0:
                time.sleep(sleep_sec)


        thread.join()



