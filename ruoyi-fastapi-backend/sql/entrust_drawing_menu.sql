-- 图纸管理菜单
-- 添加到"委外加工"菜单下

-- 先查出委外加工的menu_id（假设已存在，需根据实际ID调整）
-- 以下使用子查询自动获取

INSERT INTO sys_menu (menu_name, parent_id, order_num, path, component, menu_type, visible, status, perms, icon, create_by, create_time, update_by, update_time, remark)
SELECT '图纸管理', menu_id, 7, 'drawing', 'entrust/drawing/index', 'C', '0', '0', 'entrust:drawing:list', 'documentation', 1, NOW(), 1, NOW(), '图纸管理菜单'
FROM sys_menu WHERE menu_name = '委外加工' AND menu_type = 'M' LIMIT 1;

-- 按钮权限
INSERT INTO sys_menu (menu_name, parent_id, order_num, path, component, menu_type, visible, status, perms, icon, create_by, create_time, update_by, update_time, remark)
SELECT '图纸查询', m.menu_id, 1, '', '', 'F', '0', '0', 'entrust:drawing:query', '#', 1, NOW(), 1, NOW(), ''
FROM sys_menu m WHERE m.menu_name = '图纸管理' AND m.menu_type = 'C' AND m.perms = 'entrust:drawing:list' LIMIT 1;

INSERT INTO sys_menu (menu_name, parent_id, order_num, path, component, menu_type, visible, status, perms, icon, create_by, create_time, update_by, update_time, remark)
SELECT '图纸删除', m.menu_id, 2, '', '', 'F', '0', '0', 'entrust:drawing:delete', '#', 1, NOW(), 1, NOW(), ''
FROM sys_menu m WHERE m.menu_name = '图纸管理' AND m.menu_type = 'C' AND m.perms = 'entrust:drawing:list' LIMIT 1;

INSERT INTO sys_menu (menu_name, parent_id, order_num, path, component, menu_type, visible, status, perms, icon, create_by, create_time, update_by, update_time, remark)
SELECT '图纸下载', m.menu_id, 3, '', '', 'F', '0', '0', 'entrust:drawing:download', '#', 1, NOW(), 1, NOW(), ''
FROM sys_menu m WHERE m.menu_name = '图纸管理' AND m.menu_type = 'C' AND m.perms = 'entrust:drawing:list' LIMIT 1;

-- 给 admin 角色（role_id=1）授权
INSERT INTO sys_role_menu (role_id, menu_id)
SELECT 1, menu_id FROM sys_menu WHERE perms IN ('entrust:drawing:list', 'entrust:drawing:query', 'entrust:drawing:delete', 'entrust:drawing:download');
