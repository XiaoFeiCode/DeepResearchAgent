import unittest

from api.services.ragflow_service import _caption_priority, _is_visual_chunk


class RagflowImageChunkTests(unittest.TestCase):
    def test_plain_document_text_is_not_treated_as_a_figure(self):
        self.assertFalse(_is_visual_chunk({"content": "2.1 信息分类组织与页面布局设计"}))

    def test_multimodal_analysis_and_figure_captions_are_visual_chunks(self):
        self.assertTrue(_is_visual_chunk({"content": "### Analysis of the Image"}))
        self.assertTrue(_is_visual_chunk({"content": 'Fig.3 "APP interface" 图3 APP界面'}))

    def test_caption_is_preferred_over_generated_analysis(self):
        analysis = {"content": "### Analysis of the Image\nFig.3 APP interface"}
        caption = {"content": "Fig.3 APP interface 图3 APP界面"}
        self.assertGreater(_caption_priority(caption), _caption_priority(analysis))


if __name__ == "__main__":
    unittest.main()
