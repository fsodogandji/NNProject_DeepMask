from CocoUtils import *
from PIL import Image, ImageOps
import os
from math import pow
from Constants import input_pic_size, max_centered_object_dimension, translation_shift, scale_deformation


class ExamplesGenerator(object):
    def __init__(self, data_dir, data_type, output_dir, debug=False):
        self.coco_utils = CocoUtils(data_dir, data_type)
        self.images_dir = '%s/annotations/images/' % data_dir
        self.window_size = input_pic_size
        self.max_object_size = max_centered_object_dimension
        self.debug = debug
        self.output_dir = output_dir

    def generate_positive_examples(self, examples_to_generate=None):
        stats = ExampleGeneratorStats()

        image_ids_and_names = self.coco_utils.get_images_data()

        for pic_data in image_ids_and_names:
            pic_id = pic_data['id']
            pic_path = self.images_dir + pic_data['file_name']

            if not os.path.isfile(pic_path):
                stats.img_not_found += 1
                if self.debug:
                    print 'image %d does not exist' % pic_id
                continue  # img does not exist

            stats.img_exists += 1

            annotations = self.coco_utils.get_img_annotations(pic_id)
            if not self.coco_utils.are_legal_anotations(annotations):
                if self.debug:
                    print 'illegal annotations for picture %s' % pic_id
                stats.img_with_illegal_annotations += 1
                continue

            stats.img_with_legal_annotations += 1

            for segmentation in annotations:
                self.create_positive_example(pic_data, segmentation, pic_path, pic_id, stats)

            if examples_to_generate == stats.seg_success:
                # generated enough
                break

        return stats

    def create_positive_example(self, pic_data, segmentation, pic_path, pic_id, stats):

        seg_id = segmentation['id']

        # bbs - [x y w h]
        bbox = segmentation['bbox']
        seg_height = bbox[3]
        seg_width = bbox[2]

        max_dim = round(max(seg_height, seg_width))
        if max_dim > self.max_object_size:
            if self.debug:
                print 'segment %d in picture %d is too big' % (seg_id, pic_id)
            stats.seg_too_big += 1
            return

        if max_dim < self.max_object_size:
            if self.debug:
                print 'segment %d in picture %d is too small' % (seg_id, pic_id)
            stats.seg_too_small += 1
            return

        pic_height = pic_data['height']
        pic_width = pic_data['width']

        seg_center_x = bbox[0] + seg_width / 2
        seg_center_y = bbox[1] + seg_height / 2

        patch_min_x = seg_center_x - self.window_size/2
        patch_max_x = seg_center_x + self.window_size/2
        patch_min_y = seg_center_y - self.window_size/2
        patch_max_y = seg_center_y + self.window_size/2

        if self.patch_exceeds_pic(patch_min_x, patch_min_y, patch_max_x, patch_max_y, pic_width, pic_height):
            if self.debug:
                print 'segment %d in picture %d cannot be centered (too close to the edges)' % (seg_id, pic_id)
            stats.seg_too_close_to_edges += 1
            return

        im_arr = io.imread(pic_path)
         # get_annotation_mask
        seg_im = self.coco_utils.get_annotation_image(segmentation, pic_width, pic_height)

        self.create_noisy_and_regular_pictures(im_arr, seg_im, patch_min_x, patch_max_x, patch_min_y, patch_max_y,
                                               pic_width, pic_height, pic_id, seg_id)
        stats.seg_success += 1

    def create_noisy_and_regular_pictures(self, im_arr, seg_im, patch_min_x, patch_max_x, patch_min_y, patch_max_y,
                                          pic_width, pic_height, pic_id, seg_id):
        x_offsets = [-translation_shift, 0, translation_shift]
        y_offsets = [-translation_shift, 0, translation_shift]
        x_scales = {pow(2.0, scale_deformation), 1, pow(2.0, -scale_deformation)}
        y_scales = {pow(2.0, scale_deformation), 1, pow(2.0, -scale_deformation)}

        for x_scale in x_scales:
            for y_scale in y_scales:
                for x_offset in x_offsets:
                    for y_offset in y_offsets:
                        cur_patch_min_x = (x_scale * patch_min_x) + x_offset
                        cur_patch_max_x = (x_scale * patch_max_x) + x_offset
                        cur_patch_min_y = (y_scale * patch_min_y) + y_offset
                        cur_patch_max_y = (y_scale * patch_max_y) + y_offset

                        if not self.patch_exceeds_pic(cur_patch_min_x, cur_patch_min_y, cur_patch_max_x, cur_patch_max_y,
                                                      pic_width, pic_height):
                            # TODO- if the mask also does not cut

                            patch_im_arr = im_arr[cur_patch_min_y:cur_patch_max_y, cur_patch_min_x:cur_patch_max_x]
                            patch_im = Image.fromarray(patch_im_arr)
                            patch_im = patch_im.resize((self.window_size, self.window_size))
                            patch_im.save(self.create_path('im', pic_id, seg_id, x_offset, y_offset, x_scale, y_scale))

                            patch_seg_im = seg_im.crop((int(cur_patch_min_x), int(cur_patch_min_y),
                                                        int(cur_patch_max_x), int(cur_patch_max_y)))
                            patch_seg_im = patch_seg_im.resize((self.window_size, self.window_size))
                            patch_seg_im.save(self.create_path('mask', pic_id, seg_id, x_offset, y_offset, x_scale, y_scale))

                            if self.debug:
                                patch_im.show()
                                patch_seg_im.show()

                            self.create_and_save_mirror(patch_seg_im, patch_im, pic_id, seg_id, x_offset, y_offset, x_scale, y_scale)

    def create_and_save_mirror(self, mask, im_patch, pic_id, seg_id, x_offset, y_offset, x_scale, y_scale):
        mir_im = ImageOps.mirror(im_patch)
        mir_im.save(self.create_path('mir-im', pic_id, seg_id, x_offset, y_offset, x_scale, y_scale))
        mir_mask = ImageOps.mirror(mask)
        mir_mask.save(self.create_path('mir-mask', pic_id, seg_id, x_offset, y_offset, x_scale, y_scale))

    def create_path(self, im_type, pic_id, seg_id, offset_x, offset_y, x_scale, y_scale):
        return str('%s/%d-%d-%d-%d-%d-%d-%s.png' % (self.output_dir, pic_id, seg_id, offset_x, offset_y,
                                                    x_scale, y_scale, im_type))
    # TODO- fix scale file name

    def patch_exceeds_pic(self, patch_min_x, patch_min_y, patch_max_x, patch_max_y, pic_width, pic_height):
        return patch_min_x < 0 or patch_min_y < 0 or patch_max_x > pic_width or patch_max_y > pic_height


class ExampleGeneratorStats(object):
    def __init__(self):
        self.img_not_found = 0
        self.img_exists = 0
        self.img_with_illegal_annotations = 0
        self.img_with_legal_annotations = 0

        self.seg_too_big = 0
        self.seg_too_small = 0
        self.seg_too_close_to_edges = 0
        self.seg_success = 0

    def __str__(self):
        return str('imgs not found: %d\n'
                   'imgs found: %d\n'
                   '\timgs with illegal annotations: %d\n'
                   '\timgs with legal annotations: %d\n'
                   '\t\tseg too big: %d\n'
                   '\t\tseg too small: %d\n'
                   '\t\tseg too close to edges: %d\n'
                   '\t\tseg success: %d\n'
                   % (self.img_not_found, self.img_exists, self.img_with_illegal_annotations,
                      self.img_with_legal_annotations, self.seg_too_big, self.seg_too_small,
                      self.seg_too_close_to_edges, self.seg_success))


eg = ExamplesGenerator('..', 'train2014', 'Results')
stats_res = eg.generate_positive_examples()
print stats_res
