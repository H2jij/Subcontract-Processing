-- 图纸管理菜单（修复版：直接用 parent_id=9400）

-- 检查是否已存在，避免重复
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM sys_menu WHERE perms = 'entrust:drawing:list') THEN
        -- 插入图纸管理菜单
        INSERT INTO sys_menu (menu_name, parent_id, order_num, path, component, menu_type, visible, status, perms, icon, create_by, create_time, update_by, update_time, remark)
        VALUES ('图纸管理', 9400, 7, 'drawing', 'entrust/drawing/index', 'C', '0', '0', 'entrust:drawing:list', 'documentation', 1, NOW(), 1, NOW(), '图纸管理菜单');

        -- 按钮权限：图纸查询
        INSERT INTO sys_menu (menu_name, parent_id, order_num, path, component, menu_type, visible, status, perms, icon, create_by, create_time, update_by, update_time, remark)
        SELECT '图纸查询', m.menu_id, 1, '', '', 'F', '0', '0', 'entrust:drawing:query', '#', 1, NOW(), 1, NOW(), ''
        FROM sys_menu m WHERE m.perms = 'entrust:drawing:list' LIMIT 1;

        -- 按钮权限：图纸删除
        INSERT INTO sys_menu (menu_name, parent_id, order_num, path, component, menu_type, visible, status, perms, icon, create_by, create_time, update_by, update_time, remark)
        SELECT '图纸删除', m.menu_id, 2, '', '', 'F', '0', '0', 'entrust:drawing:delete', '#', 1, NOW(), 1, NOW(), ''
        FROM sys_menu m WHERE m.perms = 'entrust:drawing:list' LIMIT 1;

        -- 按钮权限：图纸下载
        INSERT INTO sys_menu (menu_name, parent_id, order_num, path, component, menu_type, visible, status, perms, icon, create_by, create_time, update_by, update_time, remark)
        SELECT '图纸下载', m.menu_id, 3, '', '', 'F', '0', '0', 'entrust:drawing:download', '#', 1, NOW(), 1, NOW(), ''
        FROM sys_menu m WHERE m.perms = 'entrust:drawing:list' LIMIT 1;

        -- 给 admin 角色（role_id=1）授权
        INSERT INTO sys_role_menu (role_id, menu_id)
        SELECT 1, menu_id FROM sys_menu WHERE perms IN ('entrust:drawing:list', 'entrust:drawing:query', 'entrust:drawing:delete', 'entrust:drawing:download');

        RAISE NOTICE '菜单插入成功';
    ELSE
        RAISE NOTICE '图纸管理菜单已存在，跳过';
    END IF;
END $$;
