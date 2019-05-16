"""Object Detection on Spark using TensorFlow.

Consumes video frames from an Kafka Endpoint, process it on spark, produces
a result containing annotate video frame and sends it to another topic of the
same Kafka Endpoint.

"""
# Utility imports
from __future__ import print_function
import base64
import json
import numpy as np
from io import StringIO
from timeit import default_timer as timer
from PIL import Image
import datetime as dt
from random import randint

# Streaming imports
from pyspark import SparkContext
from pyspark.streaming import StreamingContext
from pyspark.streaming.kafka import KafkaUtils
from kafka import KafkaProducer
import cv2

from core.services import SuspicionDetection


class Spark_Object_Detector():
    """Stream WebCam Images to Kafka Endpoint.

    Keyword arguments:
    source -- Index of Video Device or Filename of Video-File
    interval -- Interval for capturing images in seconds (default 5)
    server -- Host + Port of Kafka Endpoint (default '127.0.0.1:9092')
    """

    def __init__(self,
                 interval=10,
                 topic_to_consume='test',
                 topic_for_produce='resultstream',
                 kafka_endpoint='127.0.0.1:9092'):
        self.detector = SuspicionDetection.SuspicionDetection()
        self.detector.enable_yolo_detection()
        """Initialize Spark & TensorFlow environment."""
        self.topic_to_consume = topic_to_consume
        self.topic_for_produce = topic_for_produce
        self.kafka_endpoint = kafka_endpoint
        
        # Create Kafka Producer for sending results
        self.producer = KafkaProducer(bootstrap_servers=kafka_endpoint)

        sc = SparkContext(appName='PyctureStream')
        self.ssc = StreamingContext(sc, interval)  # , 3)

        # Make Spark logging less extensive
        log4jLogger = sc._jvm.org.apache.log4j
        log_level = log4jLogger.Level.ERROR
        log4jLogger.LogManager.getLogger('org').setLevel(log_level)
        log4jLogger.LogManager.getLogger('akka').setLevel(log_level)
        log4jLogger.LogManager.getLogger('kafka').setLevel(log_level)
        self.logger = log4jLogger.LogManager.getLogger(__name__)

     

    def start_processing(self):
        """Start consuming from Kafka endpoint and detect objects."""
        kvs = KafkaUtils.createDirectStream(self.ssc,
                                            [self.topic_to_consume],
                                            {'metadata.broker.list': self.kafka_endpoint}
                                            )
        kvs.foreachRDD(self.handler)
        self.ssc.start()
        self.ssc.awaitTermination()



    def initilize_vigilancia_detector(self):
        self.objects_detector_prediction = []
        

    def load_image_into_numpy_array(self, image):
        """Convert PIL image to numpy array."""
        (im_width, im_height) = image.size
        return np.array(image.getdata()).reshape(
            (im_height, im_width, 3)).astype(np.uint8)

    
    def detect_objects(self, event):
        """Use TensorFlow Model to detect objects."""
        # Load the image data from the json into PIL image & numpy array
        decoded = base64.b64decode(event['image'])
        filename = 'C:\\Users\\hp\\Desktop\\codev1frame.jpg'  # I assume you have a way of picking unique filenames
        with open(filename, 'wb') as f:
            f.write(decoded)
        img = cv2.imread(filename)
        # Prepare object for sending to endpoint
        result = {'timestamp': event['timestamp'],
                  'camera_id': event['camera_id'],
                  'image': self.get_box_plot(img)
                  }
        return json.dumps(result)

    def get_box_plot(self,img):
        self.detector.detect(img)
        frame = self.detector.plot_objects(img)
        cv2.imwrite("abc.jpg",frame)
        img = cv2.imread("abc.jpg")
        img = cv2.imencode('.jpg', img)
        img_as_text = base64.b64encode(img).decode('utf-8')
        return img_as_text

    def handler(self, timestamp, message):
        """Collect messages, detect object and send to kafka endpoint."""
        records = message.collect()
        # For performance reasons, we only want to process the newest message
        # for every camera_id
        to_process = {}
        self.logger.info( '\033[3' + str(randint(1, 7)) + ';1m' +  # Color
            '-' * 25 +
            '[ NEW MESSAGES: ' + str(len(records)) + ' ]'
            + '-' * 25 +
            '\033[0m' # End color
            )
        dt_now = dt.datetime.now()
        for record in records:
            event = json.loads(record[1])
            self.logger.info('Received Message: ' +
                             event['camera_id'] + ' - ' + event['timestamp'])
            dt_event = dt.datetime.strptime(
                event['timestamp'], '%Y-%m-%dT%H:%M:%S.%f')
            delta = dt_now - dt_event
            if delta.seconds > 3:
                continue
            to_process[event['camera_id']] = event

        if len(to_process) == 0:
            self.logger.info('Skipping processing...')

        for key, event in to_process.items():
            self.logger.info('Processing Message: ' +
                             event['camera_id'] + ' - ' + event['timestamp'])
            start = timer()
            detection_result = self.detect_objects(event)
            end = timer()
            delta = end - start
            self.logger.info('Done after ' + str(delta) + ' seconds.')
            self.producer.send(self.topic_for_produce, detection_result.encode('utf-8'))
            self.logger.info('Sent image to Kafka endpoint.')
            # self.producer.flush()


if __name__ == '__main__':
    sod = Spark_Object_Detector(
        interval=1,
        topic_to_consume='test',
        topic_for_produce='resultstream',
        kafka_endpoint='127.0.0.1:9092')
    sod.start_processing()