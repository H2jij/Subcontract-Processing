import request from '@/utils/request'

// 图纸列表
export function listDrawings(params) {
  return request({
    url: '/entrust/drawing/list',
    method: 'get',
    params,
  })
}

// 批量查找图纸
export function lookupDrawings(data) {
  return request({
    url: '/entrust/drawing/lookup',
    method: 'post',
    data,
  })
}

// 手动拆图
export function manualSplit(data) {
  return request({
    url: '/entrust/drawing/split',
    method: 'post',
    data,
  })
}

// 预览原图零件列表
export function previewAssembly(moldCode) {
  return request({
    url: `/entrust/drawing/preview/${moldCode}`,
    method: 'get',
  })
}

// 下载图纸
export function downloadDrawing(drawingId) {
  return `/entrust/drawing/download/${drawingId}`
}

// 删除图纸
export function deleteDrawing(drawingId) {
  return request({
    url: `/entrust/drawing/${drawingId}`,
    method: 'delete',
  })
}
