import numpy as np
from os import path as osp

from mmdet3d.core import show_seg_result
from mmdet.datasets import DATASETS
from mmseg.datasets import DATASETS as SEG_DATASETS
from .custom_3d_seg import Custom3DSegDataset
from .pipelines import Compose


@DATASETS.register_module()
@SEG_DATASETS.register_module()
class _S3DISSegDataset(Custom3DSegDataset):
    r"""S3DIS Dataset for Semantic Segmentation Task.

    This class is the inner dataset for S3DIS. Since S3DIS has 6 areas, we
    often train on 5 of them and test on the remaining one.
    However, there is not a fixed train-test split of S3DIS. People often test
    on Area_5 as suggested by `SEGCloud <https://arxiv.org/abs/1710.07563>`_.
    But many papers also report the average results of 6-fold cross validation
    over the 6 areas (e.g. `DGCNN <https://arxiv.org/abs/1801.07829>`_).
    Therefore, we use an inner dataset for one area, and further use a dataset
    wrapper to concat all the provided data in different areas.

    Args:
        data_root (str): Path of dataset root.
        ann_file (str): Path of annotation file.
        pipeline (list[dict], optional): Pipeline used for data processing.
            Defaults to None.
        classes (tuple[str], optional): Classes used in the dataset.
            Defaults to None.
        palette (list[list[int]], optional): The palette of segmentation map.
            Defaults to None.
        modality (dict, optional): Modality to specify the sensor data used
            as input. Defaults to None.
        test_mode (bool, optional): Whether the dataset is in test mode.
            Defaults to False.
        ignore_index (int, optional): The label index to be ignored, e.g. \
            unannotated points. If None is given, set to len(self.CLASSES).
            Defaults to None.
        scene_idxs (np.ndarray | str, optional): Precomputed index to load
            data. For scenes with many points, we may sample it several times.
            Defaults to None.
        label_weight (np.ndarray | str, optional): Precomputed weight to \
            balance loss calculation. If None is given, compute from data.
            Defaults to None.
    """
    CLASSES = ('ceiling', 'floor', 'wall', 'beam', 'column', 'window', 'door',
               'table', 'chair', 'sofa', 'bookcase', 'board', 'clutter')

    VALID_CLASS_IDS = tuple(range(13))

    ALL_CLASS_IDS = tuple(range(14))  # possibly with 'stair' class

    PALETTE = [[0, 255, 0], [0, 0, 255], [0, 255, 255], [255, 255, 0],
               [255, 0, 255], [100, 100, 255], [200, 200, 100],
               [170, 120, 200], [255, 0, 0], [200, 100, 100], [10, 200, 100],
               [200, 200, 200], [50, 50, 50]]

    def __init__(self,
                 data_root,
                 ann_file,
                 pipeline=None,
                 classes=None,
                 palette=None,
                 modality=None,
                 test_mode=False,
                 ignore_index=None,
                 scene_idxs=None,
                 label_weight=None):

        super().__init__(
            data_root=data_root,
            ann_file=ann_file,
            pipeline=pipeline,
            classes=classes,
            palette=palette,
            modality=modality,
            test_mode=test_mode,
            ignore_index=ignore_index,
            scene_idxs=scene_idxs,
            label_weight=label_weight)

    def get_ann_info(self, index):
        """Get annotation info according to the given index.

        Args:
            index (int): Index of the annotation data to get.

        Returns:
            dict: annotation information consists of the following keys:

                - pts_semantic_mask_path (str): Path of semantic masks.
        """
        # Use index to get the annos, thus the evalhook could also use this api
        info = self.data_infos[index]

        pts_semantic_mask_path = osp.join(self.data_root,
                                          info['pts_semantic_mask_path'])

        anns_results = dict(pts_semantic_mask_path=pts_semantic_mask_path)
        return anns_results

    def _build_default_pipeline(self):
        """Build the default pipeline for this dataset."""
        pipeline = [
            dict(
                type='LoadPointsFromFile',
                coord_type='DEPTH',
                shift_height=False,
                use_color=True,
                load_dim=6,
                use_dim=[0, 1, 2, 3, 4, 5]),
            dict(
                type='LoadAnnotations3D',
                with_bbox_3d=False,
                with_label_3d=False,
                with_mask_3d=False,
                with_seg_3d=True),
            dict(
                type='PointSegClassMapping',
                valid_cat_ids=self.VALID_CLASS_IDS,
                max_cat_id=np.max(self.ALL_CLASS_IDS)),
            dict(
                type='DefaultFormatBundle3D',
                with_label=False,
                class_names=self.CLASSES),
            dict(type='Collect3D', keys=['points', 'pts_semantic_mask'])
        ]
        return Compose(pipeline)

    def show(self, results, out_dir, show=True, pipeline=None):
        """Results visualization.

        Args:
            results (list[dict]): List of bounding boxes results.
            out_dir (str): Output directory of visualization result.
            show (bool): Visualize the results online.
            pipeline (list[dict], optional): raw data loading for showing.
                Default: None.
        """
        assert out_dir is not None, 'Expect out_dir, got none.'
        pipeline = self._get_pipeline(pipeline)
        for i, result in enumerate(results):
            data_info = self.data_infos[i]
            pts_path = data_info['pts_path']
            file_name = osp.split(pts_path)[-1].split('.')[0]
            points, gt_sem_mask = self._extract_data(
                i, pipeline, ['points', 'pts_semantic_mask'], load_annos=True)
            points = points.numpy()
            pred_sem_mask = result['semantic_mask'].numpy()
            show_seg_result(points, gt_sem_mask,
                            pred_sem_mask, out_dir, file_name,
                            np.array(self.PALETTE), self.ignore_index, show)

    def get_scene_idxs_and_label_weight(self, scene_idxs, label_weight):
        """Compute scene_idxs for data sampling and label weight for loss \
        calculation.

        We sample more times for scenes with more points. Label_weight is
        inversely proportional to number of class points.
        """
        # when testing, we load one whole scene every time
        # and we don't need label weight for loss calculation
        if not self.test_mode and scene_idxs is None:
            raise NotImplementedError(
                'please provide re-sampled scene indexes for training')

        return super().get_scene_idxs_and_label_weight(scene_idxs,
                                                       label_weight)


@DATASETS.register_module()
class S3DISSegDataset(_S3DISSegDataset):
    r"""S3DIS Dataset for Semantic Segmentation Task.

    This class serves as the API for experiments on the S3DIS Dataset.
    It wraps the provided datasets of different areas.
    We don't use `mmdet.datasets.dataset_wrappers.ConcatDataset` because we
    need to concat the `scene_idxs` and `label_weights` of different areas.

    Please refer to the `google form <https://docs.google.com/forms/d/e/1FAIpQL
    ScDimvNMCGhy_rmBA2gHfDu3naktRm6A8BPwAWWDv-Uhm6Shw/viewform?c=0&w=1>`_ for
    data downloading.

    Args:
        data_root (str): Path of dataset root.
        ann_files (list[str]): Path of several annotation files.
        pipeline (list[dict], optional): Pipeline used for data processing.
            Defaults to None.
        classes (tuple[str], optional): Classes used in the dataset.
            Defaults to None.
        palette (list[list[int]], optional): The palette of segmentation map.
            Defaults to None.
        modality (dict, optional): Modality to specify the sensor data used
            as input. Defaults to None.
        test_mode (bool, optional): Whether the dataset is in test mode.
            Defaults to False.
        ignore_index (int, optional): The label index to be ignored, e.g. \
            unannotated points. If None is given, set to len(self.CLASSES).
            Defaults to None.
        scene_idxs (list[np.ndarray] | list[str], optional): Precomputed index
            to load data. For scenes with many points, we may sample it several
            times. Defaults to None.
        label_weights (list[np.ndarray] | list[str], optional): Precomputed
            weight to balance loss calculation. If None is given, compute from
            data. Defaults to None.
    """

    def __init__(self,
                 data_root,
                 ann_files,
                 pipeline=None,
                 classes=None,
                 palette=None,
                 modality=None,
                 test_mode=False,
                 ignore_index=None,
                 scene_idxs=None,
                 label_weights=None):

        # make sure that ann_files, scene_idxs and label_weights have same len
        ann_files = self._check_ann_files(ann_files)
        scene_idxs = self._check_scene_idxs(scene_idxs, len(ann_files))
        label_weights = self._check_label_weights(label_weights,
                                                  len(ann_files))

        # initialize some attributes as datasets[0]
        super().__init__(
            data_root=data_root,
            ann_file=ann_files[0],
            pipeline=pipeline,
            classes=classes,
            palette=palette,
            modality=modality,
            test_mode=test_mode,
            ignore_index=ignore_index,
            scene_idxs=scene_idxs[0],
            label_weight=label_weights[0])

        datasets = [
            _S3DISSegDataset(
                data_root=data_root,
                ann_file=ann_files[i],
                pipeline=pipeline,
                classes=classes,
                palette=palette,
                modality=modality,
                test_mode=test_mode,
                ignore_index=ignore_index,
                scene_idxs=scene_idxs[i],
                label_weight=label_weights[i]) for i in range(len(ann_files))
        ]

        # data_infos, scene_idxs, label_weight need to be concat
        self.concat_data_infos([dst.data_infos for dst in datasets])
        self.concat_scene_idxs([dst.scene_idxs for dst in datasets])
        self.concat_label_weight([dst.label_weight for dst in datasets])

        # set group flag for the sampler
        if not self.test_mode:
            self._set_group_flag()

    def concat_data_infos(self, data_infos):
        """Concat data_infos from several datasets to form self.data_infos.

        Args:
            data_infos (list[list[dict]])
        """
        self.data_infos = [
            info for one_data_infos in data_infos for info in one_data_infos
        ]

    def concat_scene_idxs(self, scene_idxs):
        """Concat scene_idxs from several datasets to form self.scene_idxs.

        Needs to manually add offset to scene_idxs[1, 2, ...].

        Args:
            scene_idxs (list[np.ndarray])
        """
        self.scene_idxs = np.array([], dtype=np.int32)
        offset = 0
        for one_scene_idxs in scene_idxs:
            self.scene_idxs = np.concatenate(
                [self.scene_idxs, one_scene_idxs + offset]).astype(np.int32)
            offset = np.unique(self.scene_idxs).max() + 1

    def concat_label_weight(self, label_weights):
        """Concat label_weight from several datasets to form self.label_weight.

        Args:
            label_weights (list[np.ndarray])
        """
        # TODO: simply average them?
        self.label_weight = np.array(label_weights).mean(0).astype(np.float32)

    @staticmethod
    def _duplicate_to_list(x, num):
        """Repeat x `num` times to form a list."""
        return [x for _ in range(num)]

    def _check_ann_files(self, ann_file):
        """Make ann_files as list/tuple."""
        # ann_file could be str
        if not isinstance(ann_file, (list, tuple)):
            ann_file = self._duplicate_to_list(ann_file, 1)
        return ann_file

    def _check_scene_idxs(self, scene_idx, num):
        """Make scene_idxs as list/tuple."""
        if scene_idx is None:
            return self._duplicate_to_list(scene_idx, num)
        # scene_idx could be str, np.ndarray, list or tuple
        if isinstance(scene_idx, str):  # str
            return self._duplicate_to_list(scene_idx, num)
        if isinstance(scene_idx[0], str):  # list of str
            return scene_idx
        if isinstance(scene_idx[0], (list, tuple, np.ndarray)):  # list of idx
            return scene_idx
        # single idx
        return self._duplicate_to_list(scene_idx, num)

    def _check_label_weights(self, label_weight, num):
        """Make label_weights as list/tuple."""
        if label_weight is None:
            return self._duplicate_to_list(label_weight, num)
        # label_weight could be str, np.ndarray, list or tuple
        if isinstance(label_weight, str):  # str
            return self._duplicate_to_list(label_weight, num)
        if isinstance(label_weight[0], str):  # list of str
            return label_weight
        if isinstance(label_weight[0], (list, tuple, np.ndarray)):  # list of w
            return label_weight
        # single weight
        return self._duplicate_to_list(label_weight, num)
